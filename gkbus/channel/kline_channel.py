from abc import abstractmethod

from .channel_abc import ChannelABC


class KLineChannel(ChannelABC):
	'''
	K-Line - a half duplex byte stream
	'''

	def __init__ (self, baudrate: int = 10400) -> None:
		self.baudrate = baudrate

	@abstractmethod
	def read (self, size: int, timeout: float) -> bytes:
		'''
		Read exactly `size` bytes

		:param timeout: seconds to wait for all of them
		:raises TimeoutException: fewer than `size` bytes arrived in time
		'''

	@abstractmethod
	def write (self, data: bytes) -> int:
		'''
		Send bytes. Anything the bus echoes back is consumed, it won't show up in read()

		:return: number of bytes written
		'''

	@abstractmethod
	def set_baudrate (self, baudrate: int) -> None:
		'''
		Change the baudrate. Applied immediately if the channel is open, on open otherwise
		'''

	def get_baudrate (self) -> int:
		return self.baudrate

	@abstractmethod
	def reset_buffers (self) -> None:
		'''
		Throw away anything waiting in the input and output buffers
		'''

	@abstractmethod
	def fast_init (self, payload: bytes) -> bytes:
		'''
		Wake the bus up with ISO 14230 fast init and send the payload
		(usually a StartCommunication request). Implementations may retry with adjusted timing.
		The input buffer is left empty

		:return: whatever came back during the wake-up, only useful for logging
		'''
