import logging
import math
import time
from collections import deque
from threading import Lock
from typing import TYPE_CHECKING

from ...channel import CanChannel, CanFilter, CanFrame, IsoTpParams
from ...channel.can_frame import EXTENDED_ID_MASK, STANDARD_ID_MASK
from ...exceptions import ChannelException, TimeoutException
from .constants import CAN_29BIT_ID, CAN_ID_BOTH, CAN_ID_SIZE, TX_MSG_TYPE, FilterType, Protocol
from .j2534_isotp_link import J2534IsoTpLink
from .library import J2534Error, J2534Library, J2534Message

if TYPE_CHECKING:
	from .j2534_device import J2534Device

logger = logging.getLogger(__name__)

#: J2534-1 guarantees 10 filters per channel, the OpenPort has no more
MAX_FILTERS = 10
#: how long send() waits for the frame to be acknowledged on the bus
SEND_TIMEOUT_MS = 200
#: how long a sent frame is looked out for among the received ones
OWN_FRAME_TTL = 1.0
OWN_FRAMES_MAX = 64

class J2534CanChannel(CanChannel):
	'''
	CAN bus on a J2534 adapter (PassThruConnect CAN), 11 and 29 bit identifiers.

	J2534 receives nothing until a filter lets it through, so the receive filters are set up
	once send() or recv() is first used - a channel only used for ISO-TP doesn't queue up
	frames nobody reads. Up to 10 filters are applied by the adapter, more than that by recv().

	A J2534 adapter receives the frames it sent itself, like any other node on the bus;
	recv() drops them, so it behaves like the other CAN channels.
	ISO-TP links from isotp() are done by the adapter
	'''

	def __init__ (
		self,
		device: 'J2534Device',
		bitrate: int = 500_000,
		filters: list[CanFilter] | None = None,
	) -> None:
		super().__init__(bitrate, filters)
		self.device = device
		self._library: J2534Library | None = None
		self._channel_id: int | None = None
		self._filter_ids: list[int] = []
		self._filters_installed = False
		#: (sent at, identifier, data, extended) of frames we sent, to drop them in recv()
		self._sent: deque[tuple[float, int, bytes, bool]] = deque(maxlen=OWN_FRAMES_MAX)
		self._sent_lock = Lock()
		self._links: list[J2534IsoTpLink] = []
		self._lock = Lock()

	def open (self) -> None:
		with self._lock:
			if self._channel_id is not None:
				return
			library, device_id = self.device.handle()
			self._channel_id = library.connect(device_id, Protocol.CAN, CAN_ID_BOTH, self.bitrate)
			self._library = library
			if self._filters:
				try:
					self._install_filters()
				except J2534Error:
					self._disconnect()
					raise

	def is_open (self) -> bool:
		return self._channel_id is not None

	def close (self) -> None:
		with self._lock:
			if self._channel_id is None:
				return
			for link in list(self._links):
				link.close()
			self._disconnect()

	def send (self, frame: CanFrame) -> None:
		'''
		:raises TimeoutException: the frame wasn't acknowledged on the bus in time
		'''
		library, channel_id = self._open_channel()
		self._ensure_filters()
		if len(frame.data) > 8:
			raise ChannelException('CAN frame data too long: {} bytes'.format(len(frame.data)))
		extended = bool(frame.extended)
		with self._sent_lock:
			self._sent.append((time.monotonic(), frame.identifier, frame.data, extended))
		library.write_msgs(channel_id, [J2534Message(
			Protocol.CAN,
			frame.identifier.to_bytes(CAN_ID_SIZE, 'big') + frame.data,
			tx_flags=CAN_29BIT_ID if extended else 0,
		)], SEND_TIMEOUT_MS)

	def recv (self, timeout: float) -> CanFrame:
		library, channel_id = self._open_channel()
		self._ensure_filters()
		deadline = time.monotonic() + timeout
		while True:
			remaining = max(math.ceil((deadline - time.monotonic()) * 1000), 0)
			messages = library.read_msgs(channel_id, 1, remaining)
			if not messages:
				if remaining == 0:
					raise TimeoutException
				continue
			frame = self._frame(messages[0])
			if frame is not None and not self._own(frame) and self._matches_filters(frame):
				return frame

	def isotp (
		self, tx_id: int, rx_id: int, params: IsoTpParams | None = None,
	) -> J2534IsoTpLink:
		'''
		ISO-TP link done by the adapter. It runs on a J2534 channel of its own, alongside this
		one, and only one can be open at a time
		'''
		return J2534IsoTpLink(self, tx_id, rx_id, params)

	def _apply_filters (self) -> None:
		'''
		Untouched until the channel is used - see _ensure_filters()
		'''
		with self._lock:
			if self._channel_id is not None and (self._filters_installed or self._filters):
				self._install_filters()

	def _ensure_filters (self) -> None:
		if not self._filters_installed:
			with self._lock:
				if self._channel_id is not None and not self._filters_installed:
					self._install_filters()

	def _install_filters (self) -> None:
		'''
		Replace the adapter's filters with ours. Too many filters, or none, pass everything
		and recv() sorts it out
		'''
		library, channel_id = self._library, self._channel_id
		assert library is not None and channel_id is not None
		self._remove_filters()
		filters = self._filters if 0 < len(self._filters) <= MAX_FILTERS else [CanFilter(0, 0)]
		for can_filter in filters:
			mask = can_filter.can_mask & EXTENDED_ID_MASK
			flags = CAN_29BIT_ID if mask > STANDARD_ID_MASK else 0
			self._filter_ids.append(library.start_msg_filter(
				channel_id,
				FilterType.PASS,
				J2534Message(Protocol.CAN, mask.to_bytes(CAN_ID_SIZE, 'big'), tx_flags=flags),
				J2534Message(
					Protocol.CAN,
					(can_filter.can_id & mask).to_bytes(CAN_ID_SIZE, 'big'),
					tx_flags=flags,
				),
			))
		self._filters_installed = True

	def _remove_filters (self) -> None:
		library, channel_id = self._library, self._channel_id
		assert library is not None and channel_id is not None
		while self._filter_ids:
			library.stop_msg_filter(channel_id, self._filter_ids.pop())
		self._filters_installed = False

	def _own (self, frame: CanFrame) -> bool:
		'''
		Whether it's a frame we sent, coming back. Each sent frame is matched once
		'''
		now = time.monotonic()
		with self._sent_lock:
			while self._sent and now - self._sent[0][0] > OWN_FRAME_TTL:
				self._sent.popleft()
			for entry in self._sent:
				if entry[1:] == (frame.identifier, frame.data, frame.extended):
					self._sent.remove(entry)
					return True
		return False

	@staticmethod
	def _frame (message: J2534Message) -> CanFrame | None:
		'''
		None for transmit indications and anything else that isn't a received frame
		'''
		if message.rx_status & TX_MSG_TYPE or len(message.data) < CAN_ID_SIZE:
			return None
		return CanFrame(
			int.from_bytes(message.data[:CAN_ID_SIZE], 'big'),
			message.data[CAN_ID_SIZE:],
			extended=bool(message.rx_status & CAN_29BIT_ID),
		)

	def _open_channel (self) -> tuple[J2534Library, int]:
		library, channel_id = self._library, self._channel_id
		if library is None or channel_id is None:
			raise ChannelException('CAN channel is not open')
		return library, channel_id

	def _disconnect (self) -> None:
		library, channel_id = self._library, self._channel_id
		self._library = self._channel_id = None
		self._filter_ids.clear()
		self._filters_installed = False
		with self._sent_lock:
			self._sent.clear()
		if library is not None and channel_id is not None:
			try:
				library.disconnect(channel_id)
			except J2534Error as e:
				logger.warning('Closing the J2534 CAN channel failed: {}'.format(e))
