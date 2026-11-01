import logging
import time

import serial

from ...channel import KLineChannel, KLineTiming
from ...exceptions import ChannelException, OpeningChannelException, TimeoutException
from ...utils import ms_to_ns, ns_to_ms
from ..obd_pin import ObdPin

logger = logging.getLogger(__name__)

#: how long fast init listens for the StartCommunication response
FAST_INIT_RESPONSE_TIMEOUT = 0.4
#: first byte most adapters leave in the buffer after a fast init that worked
FAST_INIT_EXPECTED_RESPONSES = (b'\x00', b'\x81', b'\xC1')
#: timing offsets fast init is retried with, in turn, while the response looks off
FAST_INIT_RETRY_OFFSETS_MS = (-2, 2)
#: time to wait for the echo on top of the time it takes to transmit the bytes
ECHO_TIMEOUT_MARGIN = 1.0
#: longest single wait on the port, longer reads are made of several. Changing the port's
#: timeout reconfigures the port - on USB adapters that's control transfers (2 ms a change with
#: an FTDI on Linux, at K-Line baudrates) in the middle of the traffic - so it's left alone
#: except when a read runs into its timeout
READ_SLICE = 0.1

class SerialKLineChannel(KLineChannel):
	'''
	K-Line through a serial port (KKL cables and the like), using pyserial.
	Any pyserial URL works as the port too, e.g. loop:// for testing.

	Of the timing, P3_MIN is kept: a request goes out no sooner than P3_MIN after the last byte
	came in. That's measured when the bytes reach us, which is always a bit after they were on
	the bus, so the gap on the bus is never shorter. Requests are sent back to back (P4 = 0)
	and responses are read by their length, so P1_MAX and P4_MIN aren't used
	'''

	def __init__ (
		self,
		port: str,
		baudrate: int = 10400,
		pin: ObdPin = ObdPin.K_LINE,
		timing: KLineTiming | None = None,
	) -> None:
		'''
		:param port: serial port, for example /dev/ttyUSB0 or COM3
		:param pin: OBD pin the adapter's K-Line is wired to, just recorded
		:param timing: only P3_MIN is used, see the class description
		'''
		super().__init__(baudrate, timing)
		self.port = port
		self.pin = ObdPin(pin)
		self._serial: serial.SerialBase | None = None
		self._low_latency = False
		#: when the last bytes came in (time.perf_counter()), P3_MIN is counted from it
		self._last_rx = 0.0

	def open (self) -> None:
		if self._serial is not None:
			return
		try:
			self._serial = serial.serial_for_url(self.port, self.baudrate, timeout=READ_SLICE)
		except serial.SerialException as e:
			raise OpeningChannelException(e) from e

		try:
			self._reset_adapter()
			self._set_kline_mode()
		except (serial.SerialException, OSError) as e:
			self.close()
			raise OpeningChannelException(e) from e
		self._low_latency = self._set_low_latency(True)

	def is_open (self) -> bool:
		return self._serial is not None

	def close (self) -> None:
		if self._serial is None:
			return
		if self._low_latency:
			self._set_low_latency(False)
			self._low_latency = False
		port, self._serial = self._serial, None
		try:
			port.break_condition = False
			port.reset_input_buffer()
			port.reset_output_buffer()
		except (serial.SerialException, OSError) as e:
			logger.info('Couldn\'t flush socket buffer before closing: {}'.format(e))
		finally:
			port.close()

	def read (self, size: int, timeout: float) -> bytes:
		data = self._read(size, timeout)
		if len(data) < size:
			raise TimeoutException
		return data

	def write (self, data: bytes) -> int:
		'''
		Sent once P3_MIN has passed since the last byte came in. Returns once the echo is back,
		which also means the bytes are out
		'''
		port = self._port()
		self._wait_p3()
		bytes_written = port.write(data)

		echo = self._read(bytes_written, self._echo_timeout(bytes_written))
		if (echo != data):
			logger.error('K-Line echo different than sent payload! \nPayload: {}\nEcho: {}'.format(
				' '.join([hex(x) for x in list(data)]),
				' '.join([hex(x) for x in list(echo)])
			))

		return bytes_written

	def set_baudrate (self, baudrate: int) -> None:
		self.baudrate = baudrate
		if self._serial is not None:
			self._serial.baudrate = baudrate
			self._serial.flush()

	def reset_buffers (self) -> None:
		port = self._port()
		port.reset_input_buffer()
		port.reset_output_buffer()

	def fast_init (self, payload: bytes) -> bytes:
		'''
		Bit-banged fast init. If the response looks off, it's retried 2ms longer, then 2ms
		shorter - the timing of cheap adapters isn't exact
		'''
		response = self._fast_init(payload, timing_offset_ms=0)
		# @todo: find out if there is some way to self-test and automatically measure
		# the timing offset we should apply
		for offset in FAST_INIT_RETRY_OFFSETS_MS:
			if response[0:1] in FAST_INIT_EXPECTED_RESPONSES:
				break
			response = self._fast_init(payload, timing_offset_ms=offset)
		return response

	def _fast_init (self, payload: bytes, timing_offset_ms: int = 0) -> bytes:
		'''
		Perform FastInit by bringing the bus down for 25ms and then up for 25ms,
		followed by a payload

		:return: input buffer contents (up to 40 bytes)
		'''
		port = self._port()
		fastinit_time = ms_to_ns(25-timing_offset_ms)

		# FastInit low
		port.break_condition = True
		start_time = time.perf_counter_ns()

		# this is commented for now, as it doesn't seem to provide anything
		# other than messing with the timing. if it indeed doesn't solve
		# any issue, it'll be removed completely
		#port.flush()  # Ensure the break is sent immediately

		while (time.perf_counter_ns() - start_time) < fastinit_time:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_low = time.perf_counter_ns() - start_time

		# FastInit high
		port.break_condition = False
		start_time = time.perf_counter_ns()

		# this is commented for now, as it doesn't seem to provide anything
		# other than messing with the timing. if it indeed doesn't solve
		# any issue, it'll be removed completely
		#port.flush()  # Ensure the break is sent immediately

		while (time.perf_counter_ns() - start_time) < fastinit_time:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_high = time.perf_counter_ns() - start_time

		port.write(bytes(payload))

		'''
		Sure-fire way to clear out the incoming buffer.
		socket.reset_input_buffer() didn't provide reliable results, probably due to timing.
		Why are we clearing out the incoming buffer?
		On genuine FTDI chips and some of the knockoffs, there'd be 0x00 in the buffer,
		then the request echo, and StartCommunication response afterwards.
		...
		On some chips, there'd be no 0x00. On some chips, there'd be no echo.
		On some chips, the response would be completely malformed,
		on some chips it'd be missing first 1-4 bytes, which would offset
		the buffer and trigger "echo different than sent payload" errors.
		--
		After giving it some thought, we realized we don't care about the StartCommunication
		response. We don't have to know if fastinit was successful, the upcoming
		StartDiagnosticSession request will tell us that.

		Is this the perfect solution? Probably not, but we're dealing with non-perfect
		hardware, and we want to support all of it.
		'''
		response = self._read(40, FAST_INIT_RESPONSE_TIMEOUT)

		logger.debug('K-Line FastInit: response: {!r}, time low: {}, time high: {}'.format(
			response, ns_to_ms(elapsed_time_low), ns_to_ms(elapsed_time_high)
		))
		return response

	def _reset_adapter (self) -> None:
		'''
		Flip the Data Terminal Ready state.
		This is required on some of the knock-off adapters, which will otherwise fail
		to perform Fast Init
		'''
		port = self._port()
		port.dtr = True
		time.sleep(0.1)
		port.dtr = False
		time.sleep(0.1)

	def _set_kline_mode (self) -> None:
		'''
		Set the adapter to KLine (KKL) mode by flipping DTR and RTS to 0.
		This is required on some of the knock-off adapters, which will otherwise fail
		to perform Fast Init
		'''
		port = self._port()
		port.dtr = False
		port.rts = False
		time.sleep(0.1)

	def _set_low_latency (self, enabled: bool) -> bool:
		'''
		USB serial chips hold on to received bytes for a while before handing them over - the
		FTDI latency timer, 16 ms by default. Low latency mode (Linux only, no root needed)
		brings it down to 1 ms, so responses are in and the next request can go out sooner.
		Windows keeps the driver's setting (Device Manager, port settings, advanced)

		:return: whether the mode was changed
		'''
		set_mode = getattr(self._port(), 'set_low_latency_mode', None)
		if set_mode is None:
			return False
		try:
			set_mode(enabled)
		except (ValueError, NotImplementedError, serial.SerialException, OSError) as e:
			logger.debug('Couldn\'t set low latency mode on {}: {}'.format(self.port, e))
			return False
		return True

	def _wait_p3 (self) -> None:
		'''
		Sleep until P3_MIN has passed since the last byte came in
		'''
		wait = self._last_rx + self.timing.p3_min / 1000 - time.perf_counter()
		if wait > 0:
			time.sleep(wait)

	def _read (self, size: int, timeout: float) -> bytes:
		'''
		Up to `size` bytes - fewer if the timeout runs out first
		'''
		port = self._port()
		deadline = time.perf_counter() + timeout
		data = bytearray()
		while True:
			remaining = max(deadline - time.perf_counter(), 0)
			wait = min(remaining, READ_SLICE)
			if port.timeout != wait:
				port.timeout = wait
			chunk = port.read(size - len(data))
			if chunk:
				data += chunk
				self._last_rx = time.perf_counter()
			if len(data) >= size or remaining <= READ_SLICE:
				return bytes(data)

	def _echo_timeout (self, size: int) -> float:
		return self._transmission_time(size) + ECHO_TIMEOUT_MARGIN

	def _transmission_time (self, size: int) -> float:
		'''
		Seconds it takes to send `size` bytes, 10 bits each
		'''
		return size * 10 / self.baudrate

	def _port (self) -> serial.SerialBase:
		if self._serial is None:
			raise ChannelException('K-Line channel {} is not open'.format(self.port))
		return self._serial
