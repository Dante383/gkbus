import logging
import math
import time
from typing import TYPE_CHECKING

from ...channel import IsoTpLink, IsoTpParams
from ...channel.can_frame import STANDARD_ID_MASK
from ...exceptions import ChannelException, OpeningChannelException, TimeoutException
from .constants import (
	CAN_29BIT_ID,
	CAN_ID_SIZE,
	ISO15765_FRAME_PAD,
	START_OF_MESSAGE,
	TX_MSG_TYPE,
	Config,
	FilterType,
	Protocol,
	Status,
)
from .library import J2534Error, J2534Library, J2534Message

if TYPE_CHECKING:
	from .j2534_can_channel import J2534CanChannel

logger = logging.getLogger(__name__)

#: padding warnings already logged, one per adapter and padding byte
_padding_noted: set[tuple[str, int]] = set()

class J2534IsoTpLink(IsoTpLink):
	'''
	ISO-TP done by a J2534 adapter (PassThruConnect ISO15765): it splits and reassembles
	payloads and sends flow control itself, so a payload costs one call either way.

	Padding: frames are padded when params.padding isn't None, but some adapters can't be told
	the padding byte. The OpenPort 2.0 always pads with 0x00, whatever is asked for.
	Get one from J2534CanChannel.isotp(). Only one link can be open at a time on an adapter
	'''

	def __init__ (
		self,
		channel: 'J2534CanChannel',
		tx_id: int,
		rx_id: int,
		params: IsoTpParams | None = None,
	) -> None:
		super().__init__(tx_id, rx_id, params)
		self.channel = channel
		extended = max(tx_id, rx_id) > STANDARD_ID_MASK
		self._tx_flags = (CAN_29BIT_ID if extended else 0) | \
			(ISO15765_FRAME_PAD if self.params.padding is not None else 0)
		self._library: J2534Library | None = None
		self._channel_id: int | None = None

	def open (self) -> None:
		'''
		:raises ChannelException: the CAN channel isn't open
		:raises OpeningChannelException: another ISO-TP link is open on the adapter
		'''
		if self._channel_id is not None:
			return
		if not self.channel.is_open():
			raise ChannelException('CAN channel is not open')
		library, device_id = self.channel.device.handle()
		try:
			channel_id = library.connect(
				device_id, Protocol.ISO15765, self._tx_flags & CAN_29BIT_ID, self.channel.bitrate,
			)
		except J2534Error as e:
			if e.status == Status.ERR_CHANNEL_IN_USE:
				raise OpeningChannelException(
					'Another ISO-TP link is open on {}, only one can be at a time'.format(
						self.channel.device.description()
					)
				) from e
			raise
		self._library, self._channel_id = library, channel_id
		try:
			self._configure(library, channel_id)
		except J2534Error:
			self._disconnect()
			raise
		self.channel._links.append(self)

	def is_open (self) -> bool:
		return self._channel_id is not None

	def close (self) -> None:
		if self._channel_id is None:
			return
		if self in self.channel._links:
			self.channel._links.remove(self)
		self._disconnect()

	def send (self, data: bytes, timeout: float) -> None:
		library, channel_id = self._open_channel()
		library.write_msgs(channel_id, [J2534Message(
			Protocol.ISO15765,
			self.tx_id.to_bytes(CAN_ID_SIZE, 'big') + bytes(data),
			tx_flags=self._tx_flags,
		)], max(math.ceil(timeout * 1000), 1))

	def recv (self, timeout: float) -> bytes:
		library, channel_id = self._open_channel()
		deadline = time.monotonic() + timeout
		while True:
			remaining = max(math.ceil((deadline - time.monotonic()) * 1000), 0)
			messages = library.read_msgs(channel_id, 1, remaining)
			if not messages:
				if remaining == 0:
					raise TimeoutException
				continue
			message = messages[0]
			# transmit indications, first frame indications and echoes carry no payload
			if message.rx_status & (TX_MSG_TYPE | START_OF_MESSAGE) or \
					message.protocol != Protocol.ISO15765 or len(message.data) < CAN_ID_SIZE:
				continue
			return message.data[CAN_ID_SIZE:]

	def _configure (self, library: J2534Library, channel_id: int) -> None:
		'''
		Flow control filter pairing our identifiers, the flow control we send, padding
		'''
		flags = self._tx_flags
		library.start_msg_filter(
			channel_id,
			FilterType.FLOW_CONTROL,
			J2534Message(Protocol.ISO15765, b'\xff' * CAN_ID_SIZE, tx_flags=flags),
			J2534Message(
				Protocol.ISO15765, self.rx_id.to_bytes(CAN_ID_SIZE, 'big'), tx_flags=flags,
			),
			J2534Message(
				Protocol.ISO15765, self.tx_id.to_bytes(CAN_ID_SIZE, 'big'), tx_flags=flags,
			),
		)
		library.set_config(channel_id, Config.ISO15765_BS, self.params.blocksize)
		library.set_config(channel_id, Config.ISO15765_STMIN, self.params.stmin)
		self._configure_padding(library, channel_id)

	def _configure_padding (self, library: J2534Library, channel_id: int) -> None:
		padding = self.params.padding
		if padding is None:
			return
		fixed = self.channel.device.profile.isotp_padding
		if fixed is None:
			try:
				library.set_config(channel_id, Config.ISO15765_PAD_VALUE, padding)
				return
			except J2534Error as e:
				logger.debug('Setting the ISO-TP padding byte failed: {}'.format(e))
		elif fixed == padding:
			return
		name = self.channel.device.library.name
		if (name, padding) not in _padding_noted:
			_padding_noted.add((name, padding))
			logger.info('{} can\'t pad ISO-TP frames with 0x{:02X}, it pads with {}'.format(
				name, padding, 'its own byte' if fixed is None else '0x{:02X}'.format(fixed)
			))

	def _open_channel (self) -> tuple[J2534Library, int]:
		library, channel_id = self._library, self._channel_id
		if library is None or channel_id is None:
			raise ChannelException('ISO-TP link is not open')
		return library, channel_id

	def _disconnect (self) -> None:
		library, channel_id = self._library, self._channel_id
		self._library = self._channel_id = None
		if library is not None and channel_id is not None:
			try:
				library.disconnect(channel_id)
			except J2534Error as e:
				logger.warning('Closing the J2534 ISO-TP link failed: {}'.format(e))
