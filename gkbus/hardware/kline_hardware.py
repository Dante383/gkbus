import logging
import time

import serial
import serial.tools.list_ports
from typing_extensions import Self

from .hardware_abc import (
	HardwareABC,
	HardwarePort,
	OpeningPortException,
	RawFrame,
	TimeoutException,
)

from ..utils import ns_to_ms, ms_to_ns

logger = logging.getLogger(__name__)

class KLineHardware(HardwareABC):
	'''
	Hardware class for serial devices, using pyserial as a backend
	'''

	def __init__ (self, port: str, baudrate: int = 10400, timeout: float = 2) -> None:
		self.port, self.baudrate = port, baudrate
		self.timeout = timeout
		self._port_opened = False
		self.socket: serial.Serial = None

	def open (self) -> bool:
		try:
			self.socket = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
			self._port_opened = True
		except serial.serialutil.SerialException as e:
			raise OpeningPortException(e)
		
		self._reset_adapter()
		self._set_kline_mode()

		return True

	def read (self, length: int) -> RawFrame:
		message = self.socket.read(length)

		if (len(message) < length):
			raise TimeoutException

		return RawFrame(identifier=False, data=message)

	def write (self, frame: RawFrame) -> int:
		# @todo - this timeout is needed for now, otherwise 
		# we'll get a timeout when trying to start diagnostic session
		# find out _why_ is it needed - some magic value instead 
		# of something calculated shouldnt be required here
		time.sleep((50/1000)*2)
		data = frame.data
		bytes_written = self.socket.write(data)

		while self.socket.out_waiting > 0:
			time.sleep(0.001)

		echo = self.socket.read(bytes_written)
		if (echo != data):
			logger.error('K-Line echo different than sent payload! \nPayload: {}\nEcho: {}'.format(
				' '.join([hex(x) for x in list(data)]),
				' '.join([hex(x) for x in list(echo)])
			))

		return bytes_written

	def close (self) -> None:
		if not self.is_open():
			logger.info('Tried to close an already closed port')
			return # should this be an exception?
		try:
			self.socket.break_condition = False
			self.socket.reset_input_buffer()
			self.socket.reset_output_buffer()
		except AttributeError as e:
			logger.info('Couldn\'t flush socket buffer before closing: {}'.format(str(e)))
			
		try:
			self.socket.close()
		except AttributeError as e:
			logger.error('Couldn\'t close socket: {}'.format(str(e)))

		self._port_opened = False

	def set_timeout (self, timeout: float) -> Self:
		self.socket.timeout = timeout
		self.timeout = timeout
		return self

	def set_baudrate (self, baudrate: int) -> Self:
		self.socket.baudrate = baudrate
		self.baudrate = baudrate
		self.socket.flush()
		return self

	def _reset_adapter (self) -> None:
		'''
		Flip the Data Terminal Ready state. 
		This is required on some of the knock-off adapters which will otherwise fail to perform Fast Init
		'''
		self.socket.setDTR(1)
		time.sleep(0.1)
		self.socket.setDTR(0)
		time.sleep(0.1)

	def _set_kline_mode (self) -> None:
		'''
		Set the adapter to KLine (KKL) mode by flipping DTR and RTS to 0.
		This is required on some of the knock-off adapters which will otherwise fail to perform Fast Init
		'''
		self.socket.setDTR(0)
		self.socket.setRTS(0)
		time.sleep(0.1)

	def iso14230_fast_init (self, payload: bytes, timing_offset_ms: int = 0) -> tuple[bytes, int, int]:
		'''
		Perform FastInit by bringing the bus down for 25ms and then up for 25ms followed by a payload

		:return: input buffer contents (up to 40 bytes), elapsed time in low position (ms), elapsed time in high position (ms)
		'''

		fastinit_time = ms_to_ns(25-timing_offset_ms)

		# FastInit low
		self.socket.break_condition = True
		start_time = time.monotonic_ns()

		# this is commented for now, as it doesn't seem to provide anything
		# other than messing with the timing. if it indeed doesn't solve
		# any issue, it'll be removed completely
		#self.socket.flush()  # Ensure the break is sent immediately

		while (time.monotonic_ns() - start_time) < fastinit_time:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_low = time.monotonic_ns() - start_time

		# FastInit high
		self.socket.break_condition = False
		start_time = time.monotonic_ns()

		# this is commented for now, as it doesn't seem to provide anything
		# other than messing with the timing. if it indeed doesn't solve
		# any issue, it'll be removed completely
		#self.socket.flush()  # Ensure the break is sent immediately

		while (time.monotonic_ns() - start_time) < fastinit_time:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_high = time.monotonic_ns() - start_time
		
		self.socket.write(bytes(payload))

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
		response = self.socket.read(40)

		return response, ns_to_ms(elapsed_time_low), ns_to_ms(elapsed_time_high)

	@staticmethod
	def available_ports () -> list[HardwarePort]:
		devices = []
		for port in reversed(serial.tools.list_ports.comports()):
			devices.append(HardwarePort(port.device, port.name, port.manufacturer, port.serial_number))
		return devices