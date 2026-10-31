import logging
import math
import time
from typing import TYPE_CHECKING

from ...channel import KLineChannel, KLineTiming
from ...exceptions import ChannelException, ChannelNotSupportedException, TimeoutException
from ..obd_pin import ObdPin
from .constants import (
	ISO9141_NO_CHECKSUM,
	START_OF_MESSAGE,
	TX_MSG_TYPE,
	Config,
	FilterType,
	Protocol,
	Status,
)
from .library import J2534Error, J2534Library, J2534Message

if TYPE_CHECKING:
	from .j2534_device import J2534Device

logger = logging.getLogger(__name__)

#: J2534 timing parameters are in 0.5 ms steps
TIMING_STEPS_PER_MS = 2
#: how long write() waits for the adapter on top of P3 and the time the bytes take on the wire
WRITE_TIMEOUT_MARGIN_MS = 1000
#: fast init statuses that mean the ECU didn't answer, rather than the adapter failing
NO_ANSWER = (Status.ERR_INIT_FAILED, Status.ERR_TIMEOUT, Status.ERR_BUFFER_EMPTY)
#: connect statuses that mean this way to the pin isn't available, try the next one
ROUTE_UNAVAILABLE = (
	Status.ERR_INVALID_PROTOCOL_ID, Status.ERR_NOT_SUPPORTED, Status.ERR_PIN_INVALID,
)

class J2534KLineChannel(KLineChannel):
	'''
	ISO 14230 K-Line on a J2534 adapter (PassThruConnect ISO14230), on OBD pin 7 or, if the
	adapter can switch pins, another one.

	The adapter delivers whole messages - it frames them by the gaps between bytes (P1_MAX) -
	and the channel hands them out as the byte stream K-Line channels are. It keeps to the bus
	timing (P3_MIN, P4_MIN) itself, so writes don't sleep. Checksums are left to the transport
	'''

	def __init__ (
		self,
		device: 'J2534Device',
		baudrate: int = 10400,
		pin: ObdPin = ObdPin.K_LINE,
		timing: KLineTiming | None = None,
	) -> None:
		super().__init__(baudrate, timing)
		self.device = device
		self.pin = ObdPin(pin)
		self._library: J2534Library | None = None
		self._channel_id: int | None = None
		self._protocol: int | None = None
		self._buffer = bytearray()
		#: when the last bytes arrived, to keep P3_MIN across a reconnect
		self._last_rx = 0.0

	def open (self) -> None:
		'''
		:raises ChannelNotSupportedException: the adapter can't do K-Line on the pin
		'''
		if self._channel_id is not None:
			return
		library, device_id = self.device.handle()
		self._connect(library, device_id)

	def is_open (self) -> bool:
		return self._channel_id is not None

	def close (self) -> None:
		self._buffer.clear()
		self._disconnect()

	def read (self, size: int, timeout: float) -> bytes:
		library, channel_id = self._open_channel()
		deadline = time.monotonic() + timeout
		while len(self._buffer) < size:
			remaining = max(math.ceil((deadline - time.monotonic()) * 1000), 0)
			messages = library.read_msgs(channel_id, 1, remaining)
			if not messages:
				if remaining == 0:
					# like a serial port: what arrived of it is gone
					self._buffer.clear()
					raise TimeoutException
				continue
			message = messages[0]
			# start of message indications carry no data, echoes are consumed
			if message.rx_status & (TX_MSG_TYPE | START_OF_MESSAGE):
				continue
			self._buffer += message.data
			self._last_rx = time.monotonic()
		data = bytes(self._buffer[:size])
		del self._buffer[:size]
		return data

	def write (self, data: bytes) -> int:
		'''
		One message, sent once the adapter's P3_MIN since the last response has passed
		'''
		library, channel_id = self._open_channel()
		assert self._protocol is not None
		library.write_msgs(
			channel_id, [J2534Message(self._protocol, bytes(data))], self._write_timeout(len(data)),
		)
		return len(data)

	def set_baudrate (self, baudrate: int) -> None:
		'''
		Changed on the open channel (the OpenPort 2.0 can). Adapters that refuse it, or don't
		report the new rate back, get the channel reopened at the new rate
		'''
		self.baudrate = baudrate
		library, channel_id = self._library, self._channel_id
		if library is None or channel_id is None:
			return
		try:
			library.set_config(channel_id, Config.DATA_RATE, baudrate)
			if library.get_config(channel_id, Config.DATA_RATE) == baudrate:
				return
		except J2534Error as e:
			logger.debug('Changing the K-Line baudrate on the fly failed: {}'.format(e))
		self._reconnect()

	def set_timing (self, timing: KLineTiming) -> None:
		self.timing = timing
		if self._library is not None and self._channel_id is not None:
			self._apply_timing(self._library, self._channel_id)

	def reset_buffers (self) -> None:
		library, channel_id = self._open_channel()
		self._buffer.clear()
		library.clear_rx_buffer(channel_id)
		library.clear_tx_buffer(channel_id)

	def fast_init (self, payload: bytes) -> bytes:
		'''
		The adapter does the fast init and sends the payload, then waits for the response.
		The ECU not answering isn't an error, the next request finds out whether it listens

		:return: the ECU's response, empty if it didn't answer
		'''
		library, channel_id = self._open_channel()
		assert self._protocol is not None
		self._buffer.clear()
		library.clear_rx_buffer(channel_id)
		try:
			response = library.fast_init(channel_id, J2534Message(self._protocol, bytes(payload)))
		except J2534Error as e:
			if e.status not in NO_ANSWER:
				raise
			logger.debug('K-Line fast init: no answer: {}'.format(e))
			response = b''
		else:
			self._last_rx = time.monotonic()
		# the response is returned, not read
		library.clear_rx_buffer(channel_id)
		logger.debug('K-Line fast init: response: {}'.format(response.hex(' ')))
		return response

	def _connect (self, library: J2534Library, device_id: int) -> None:
		'''
		Connect on the pin, trying the ways the adapter might do it in turn
		'''
		for protocol, pins in self._routes():
			try:
				channel_id = library.connect(
					device_id, protocol, ISO9141_NO_CHECKSUM, self.baudrate,
				)
			except J2534Error as e:
				if self.pin == ObdPin.K_LINE or e.status not in ROUTE_UNAVAILABLE:
					raise
				logger.debug('K-Line on pin {} through 0x{:X}: {}'.format(self.pin, protocol, e))
				continue
			self._library, self._channel_id, self._protocol = library, channel_id, protocol
			try:
				if pins is not None:
					library.set_config(channel_id, Config.J1962_PINS, pins)
				self._configure(library, channel_id)
			except J2534Error as e:
				self._disconnect()
				if pins is None or e.status not in ROUTE_UNAVAILABLE:
					raise
				logger.debug('K-Line on pin {} through 0x{:X}: {}'.format(self.pin, protocol, e))
				continue
			return
		raise ChannelNotSupportedException(
			'{} can\'t do K-Line on OBD pin {}'.format(self.device.description(), int(self.pin))
		)

	def _routes (self) -> list[tuple[int, int | None]]:
		'''
		(protocol, J1962_PINS value) to try, in order. J2534-2 pin switching first, then what
		the adapter is known to do
		'''
		if self.pin == ObdPin.K_LINE:
			return [(Protocol.ISO14230, None)]
		routes: list[tuple[int, int | None]] = [(Protocol.ISO14230_PS, int(self.pin) << 8)]
		if self.pin == ObdPin.L_LINE and ObdPin.L_LINE in self.device.profile.kline_pins:
			routes.append((Protocol.ISO14230_CH2, None))
		return routes

	def _configure (self, library: J2534Library, channel_id: int) -> None:
		'''
		Receive everything, no echoes, our timing
		'''
		library.start_msg_filter(
			channel_id,
			FilterType.PASS,
			J2534Message(self._protocol or 0, b'\x00'),
			J2534Message(self._protocol or 0, b'\x00'),
		)
		library.set_config(channel_id, Config.LOOPBACK, 0)
		self._apply_timing(library, channel_id)

	def _apply_timing (self, library: J2534Library, channel_id: int) -> None:
		for parameter, value in (
			(Config.P1_MAX, self.timing.p1_max),
			(Config.P3_MIN, self.timing.p3_min),
			(Config.P4_MIN, self.timing.p4_min),
		):
			library.set_config(channel_id, parameter, round(value * TIMING_STEPS_PER_MS))

	def _reconnect (self) -> None:
		library, channel_id = self._library, self._channel_id
		assert library is not None and channel_id is not None
		self._disconnect()
		self._connect(*self.device.handle())
		# the new channel doesn't know when the ECU last spoke, keep P3_MIN ourselves
		wait = self._last_rx + self.timing.p3_min / 1000 - time.monotonic()
		if wait > 0:
			time.sleep(wait)

	def _write_timeout (self, size: int) -> int:
		'''
		In ms: P3_MIN, the bytes on the wire and P4_MIN between them, and a margin
		'''
		transmission = size * 10 * 1000 / self.baudrate + max(size - 1, 0) * self.timing.p4_min
		return math.ceil(self.timing.p3_min + transmission) + WRITE_TIMEOUT_MARGIN_MS

	def _open_channel (self) -> tuple[J2534Library, int]:
		library, channel_id = self._library, self._channel_id
		if library is None or channel_id is None:
			raise ChannelException('K-Line channel is not open')
		return library, channel_id

	def _disconnect (self) -> None:
		library, channel_id = self._library, self._channel_id
		self._library = self._channel_id = self._protocol = None
		if library is not None and channel_id is not None:
			try:
				library.disconnect(channel_id)
			except J2534Error as e:
				logger.warning('Closing the J2534 K-Line channel failed: {}'.format(e))
