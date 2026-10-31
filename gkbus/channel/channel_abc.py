from abc import ABC, abstractmethod
from typing import Self


class ChannelABC(ABC):
	'''
	One bus on a device - the K-Line or the CAN bus of an adapter. Handed out by devices.
	A channel only moves raw data (bytes, CAN frames), all protocol framing belongs to transports.

	Creating a channel doesn't open anything.
	Reads take a timeout on every call and raise TimeoutException when it runs out
	'''

	@abstractmethod
	def open (self) -> None:
		'''
		Open the channel. Does nothing if it's already open

		:raises OpeningChannelException: the channel couldn't be opened
		'''

	@abstractmethod
	def is_open (self) -> bool:
		pass

	@abstractmethod
	def close (self) -> None:
		'''
		Close the channel. Does nothing if it's already closed
		'''

	def __enter__ (self) -> Self:
		self.open()
		return self

	def __exit__ (self, *exc_info: object) -> None:
		self.close()
