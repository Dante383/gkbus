from abc import ABC 
from dataclasses import dataclass
from typing_extensions import Self

class HardwareException(IOError):
	pass

class OpeningPortException(HardwareException):
	pass

class SendingException(HardwareException):
	pass

class ReadingException(HardwareException):
	pass

class TimeoutException(ReadingException):
	pass

@dataclass
class HardwarePort:
	port: str
	port_name: str # for /dev/ttyUSB0, this would be ttyUSB0
	serial_number: str = None
	manufacturer: str = None

	def description (self) -> str:
		return '{} - {}'.format(
			self.port,
			' '.join([x for x in [self.manufacturer, self.serial_number] if x is not None])
		)

class HardwareABC(ABC):
	def __init__ (self, port: str, *args) -> None:
		'''
		Create a new hardware instance, assign arguments. No logic is executed here
		'''
		self.port = port

	def open (self) -> bool:
		'''
		Open the port
		'''
		pass

	def read (self, length: int) -> bytes:
		'''
		Read X bytes from the buffer
		'''
		pass

	def write (self, data: bytes) -> int:
		'''
		Write to the port

		:return: number of bytes written
		'''
		pass

	def close (self) -> bool:
		'''
		Close the port
		'''
		pass

	def set_baudrate (self, baudrate: int) -> Self:
		'''
		Set hardware port baudrate - where applicable

		:param int baudrate: requested baudrate in bits per second
		'''
		pass

	def get_baudrate (self) -> int:
		'''
		Get current hardware port baudrate

		:return: baudrate in bits per second
		'''
		return self.baudrate

	def set_timeout (self, timeout: float) -> Self:
		'''
		Set maximum timeout for reading

		:param float timeout: Timeout in seconds
		'''
		pass

	def get_timeout (self) -> float:
		'''
		Get the maximum timeout for reading

		:return: timeout in seconds
		'''
		return self.timeout

	@staticmethod
	def available_ports () -> list[HardwarePort]:
		'''
		Enumerate available ports

		:return: list of HardwarePort objects
		'''
		pass

	def __del__ (self) -> None:
		self.close()