import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import isotp

from ..exceptions import ChannelException, TimeoutException
from .can_frame import STANDARD_ID_MASK, CanFilter, CanFrame

if TYPE_CHECKING:
	from .can_channel import CanChannel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IsoTpParams:
	'''
	ISO-TP settings. The defaults are what gkbus always used

	:param padding: byte frames are padded to 8 bytes with, None - no padding
	:param stmin: separation time in ms the ECU should keep between consecutive frames it sends
	:param blocksize: consecutive frames the ECU may send before waiting for flow control,
		0 - no limit
	'''
	padding: int | None = 0xCC
	stmin: int = 0
	blocksize: int = 0

class IsoTpLink(ABC):
	'''
	ISO 15765-2 (ISO-TP) link between a pair of CAN identifiers: splits payloads into frames,
	handles flow control and reassembles what comes back. Get one from CanChannel.isotp().
	The channel has to be open before the link is opened
	'''

	def __init__ (self, tx_id: int, rx_id: int, params: IsoTpParams | None = None) -> None:
		self.tx_id, self.rx_id = tx_id, rx_id
		self.params = params or IsoTpParams()

	@abstractmethod
	def open (self) -> None:
		'''
		Start listening. Does nothing if the link is already open
		'''

	@abstractmethod
	def is_open (self) -> bool:
		pass

	@abstractmethod
	def close (self) -> None:
		'''
		Stop listening. Does nothing if the link is already closed
		'''

	@abstractmethod
	def send (self, data: bytes, timeout: float) -> None:
		'''
		Send a payload, blocking until all of its frames are out

		:raises TimeoutException: the transfer didn't complete in time (e.g. no flow control)
		'''

	@abstractmethod
	def recv (self, timeout: float) -> bytes:
		'''
		Receive one complete payload

		:raises TimeoutException: nothing arrived in time
		'''

	def address (self) -> isotp.Address:
		'''
		can-isotp address of this link, 29 bit if either identifier needs it
		'''
		mode = (isotp.AddressingMode.Normal_29bits
			if max(self.tx_id, self.rx_id) > STANDARD_ID_MASK
			else isotp.AddressingMode.Normal_11bits)
		return isotp.Address(mode, txid=self.tx_id, rxid=self.rx_id)

	def __enter__ (self) -> Self:
		self.open()
		return self

	def __exit__ (self, *exc_info: object) -> None:
		self.close()

class SoftwareIsoTpLink(IsoTpLink):
	'''
	ISO-TP done in Python (can-isotp) on top of the channel's send() and recv(), so it works
	on any CAN channel. While the link is open, a background thread reads the channel and
	the channel's filters are narrowed down to rx_id - nothing else should read the channel then
	'''

	def __init__ (
		self,
		channel: 'CanChannel',
		tx_id: int,
		rx_id: int,
		params: IsoTpParams | None = None,
	) -> None:
		super().__init__(tx_id, rx_id, params)
		self.channel = channel
		self._stack: isotp.TransportLayer | None = None
		self._previous_filters: list[CanFilter] = []

	def open (self) -> None:
		if self._stack is not None:
			return
		self._previous_filters = self.channel.get_filters()
		self.channel.set_filters([CanFilter.for_id(self.rx_id)])

		padded = self.params.padding is not None
		stack = isotp.TransportLayer(
			rxfn=self._rx,
			txfn=self._tx,
			address=self.address(),
			params={
				'stmin': self.params.stmin,
				'blocksize': self.params.blocksize,
				'tx_padding': self.params.padding,
				'tx_data_min_length': 8 if padded else None,
				'blocking_send': True,
			},
		)
		stack.start()
		self._stack = stack

	def is_open (self) -> bool:
		return self._stack is not None

	def close (self) -> None:
		if self._stack is None:
			return
		self._stack.stop()
		self._stack = None
		self.channel.set_filters(self._previous_filters)

	def send (self, data: bytes, timeout: float) -> None:
		try:
			self._open_stack().send(data, send_timeout=timeout)
		except isotp.BlockingSendTimeout as e:
			raise TimeoutException(e) from e
		except isotp.BlockingSendFailure as e:
			raise ChannelException(e) from e

	def recv (self, timeout: float) -> bytes:
		data = self._open_stack().recv(block=True, timeout=timeout)
		if data is None:
			raise TimeoutException
		return bytes(data)

	def _open_stack (self) -> isotp.TransportLayer:
		if self._stack is None:
			raise ChannelException('ISO-TP link is not open')
		return self._stack

	def _rx (self, timeout: float) -> isotp.CanMessage | None:
		try:
			frame = self.channel.recv(timeout)
		except TimeoutException:
			return None
		except ChannelException as e:
			# the channel went away under us - don't spin, the link is about to be closed
			logger.debug('ISO-TP link could not read the channel: {}'.format(e))
			time.sleep(timeout)
			return None
		return isotp.CanMessage(
			arbitration_id=frame.identifier,
			dlc=len(frame.data),
			data=frame.data,
			extended_id=bool(frame.extended),
		)

	def _tx (self, message: isotp.CanMessage) -> None:
		self.channel.send(CanFrame(message.arbitration_id, message.data, message.is_extended_id))
