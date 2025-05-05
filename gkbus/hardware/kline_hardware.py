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

logger = logging.getLogger(__name__)

class KLineHardware(HardwareABC):
	'''
	Hardware class for serial devices, using pyserial as a backend
	'''

	def __init__ (self, port: str, baudrate: int = 10400, timeout: float = 2) -> None:
		self.port, self.baudrate = port, baudrate
		self.timeout = timeout
		self.port_opened = False
		self.socket: serial.Serial = None

	def open (self) -> bool:
		try:
			self.socket = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
			self.port_opened = True
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
		if not self.port_opened:
			return # should this be an exception?
		try:
			self.socket.break_condition = False
			self.socket.flushInput()
			self.socket.flushOutput()
			self.socket.close()
		except AttributeError:
			pass
		self.port_opened = False

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

	def iso14230_fast_init (self, payload: bytes) -> tuple[bytes, int, int]:
		'''
		Perform FastInit by bringing the bus down for 25ms and then up for 25ms followed by a payload

		:return: response (1 byte), elapsed time in low position, elapsed time in high position
		'''

		# FastInit low
		start_time = time.perf_counter()
		self.socket.break_condition = True
		self.socket.flush()  # Ensure the break is sent immediately
		while (time.perf_counter() - start_time) < 0.025:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_low = time.perf_counter() - start_time

		# FastInit high
		start_time = time.perf_counter()
		self.socket.break_condition = False
		self.socket.flush()  # Ensure the break is sent immediately
		while (time.perf_counter() - start_time) < 0.025:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_high = time.perf_counter() - start_time
		
		# Send payload and read response
		self.socket.write(bytes(payload))
		response = self.socket.read(1) # most ECUs will respond with 0x00 after a successful init
		self.socket.read(len(payload)) # i have no idea why this is suddenly returning an echo
		return response, elapsed_time_low, elapsed_time_high

	@staticmethod
	def available_ports () -> list[HardwarePort]:
		devices = []
		for port in reversed(serial.tools.list_ports.comports()):
			devices.append(HardwarePort(port.device, port.name, port.manufacturer, port.serial_number))
		return devices