import logging
import time

import serial

from ...channel import KLineChannel
from ...exceptions import ChannelException, OpeningChannelException, TimeoutException
from ...utils import ms_to_ns, ns_to_ms

logger = logging.getLogger(__name__)

#: how long fast init listens for the StartCommunication response
FAST_INIT_RESPONSE_TIMEOUT = 0.4
#: first byte most adapters leave in the buffer after a fast init that worked
FAST_INIT_EXPECTED_RESPONSES = (b'\x00', b'\x81', b'\xC1')
#: time to wait for the echo on top of the time it takes to transmit the bytes
ECHO_TIMEOUT_MARGIN = 1.0
#: time to wait for the output buffer to drain on top of the time it takes to transmit the bytes
TX_DRAIN_MARGIN = 0.1

class SerialKLineChannel(KLineChannel):
	'''
	K-Line through a serial port (KKL cables and the like), using pyserial.
	Any pyserial URL works as the port too, e.g. loop:// for testing
	'''

	def __init__ (self, port: str, baudrate: int = 10400) -> None:
		'''
		:param port: serial port, for example /dev/ttyUSB0 or COM3
		'''
		super().__init__(baudrate)
		self.port = port
		self._serial: serial.SerialBase | None = None

	def open (self) -> None:
		if self._serial is not None:
			return
		try:
			self._serial = serial.serial_for_url(
				self.port, self.baudrate, timeout=FAST_INIT_RESPONSE_TIMEOUT
			)
		except serial.SerialException as e:
			raise OpeningChannelException(e) from e

		try:
			self._reset_adapter()
			self._set_kline_mode()
		except (serial.SerialException, OSError) as e:
			self.close()
			raise OpeningChannelException(e) from e

	def is_open (self) -> bool:
		return self._serial is not None

	def close (self) -> None:
		if self._serial is None:
			return
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
		port = self._port()
		# @todo - this timeout is needed for now, otherwise
		# we'll get a timeout when trying to start diagnostic session
		# find out _why_ is it needed - some magic value instead
		# of something calculated shouldnt be required here
		time.sleep((50/1000)*2)
		bytes_written = port.write(data)

		# bounded, so a stuck adapter can't hang us - the echo read below has its own timeout
		drain_deadline = time.monotonic() + self._transmission_time(bytes_written) + TX_DRAIN_MARGIN
		while port.out_waiting > 0 and time.monotonic() < drain_deadline:
			time.sleep(0.001)

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
		Bit-banged fast init. If the response looks off, it's retried 2ms shorter and 2ms longer -
		the timing of cheap adapters isn't exact
		'''
		response = self._fast_init(payload, timing_offset_ms=0)
		# @todo: find out if there is some way to self-test and automatically measure
		# the timing offset we should apply
		if response[0:1] not in FAST_INIT_EXPECTED_RESPONSES:
			response = self._fast_init(payload, timing_offset_ms=-2)
			response = self._fast_init(payload, timing_offset_ms=2)
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

	def _read (self, size: int, timeout: float) -> bytes:
		port = self._port()
		if port.timeout != timeout:
			port.timeout = timeout
		return port.read(size)

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
