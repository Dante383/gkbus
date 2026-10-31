from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
from typing import Self, TypeVar

from ..channel import CanChannel, CanFilter, ChannelABC, KLineChannel
from ..exceptions import ChannelInUseException, ChannelNotSupportedException

T = TypeVar('T', bound=ChannelABC)


class Bus(Enum):
	KLINE = 'kline'
	CANBUS = 'canbus'

class DeviceABC(ABC):
	'''
	Abstract device class. Device refers to the actual physical device you're using for
	communication, reached through one particular access method (serial port, J2534 library,
	SocketCAN, ...). A device hands out a channel for every bus it supports. J2534 would hand out
	K-Line and CAN bus channels, SerialKLineDevice only a K-Line channel, etc.

	Creating a device doesn't open anything, so instances returned by discover()
	are safe to list and discard.
	'''

	#: buses this device type can provide channels for
	buses: frozenset[Bus] = frozenset()

	def __init__ (self) -> None:
		self._opened = False
		self._channels: dict[Bus, ChannelABC] = {}

	def open (self) -> bool:
		'''
		Open the device, so channels can be requested from it.
		Does nothing if the device is already open
		'''
		self._opened = True
		return True

	def is_open (self) -> bool:
		return self._opened

	def close (self) -> None:
		'''
		Close the device and any channels it handed out.
		Does nothing if the device is already closed
		'''
		for channel in self._channels.values():
			if channel.is_open():
				channel.close()
		self._channels.clear()
		self._opened = False

	def kline (self, baudrate: int = 10400) -> KLineChannel:
		'''
		Get the K-Line channel of this device. Opens the device (not the channel) if it wasn't open.
		The channel isn't opened - open it yourself, or let the transport do it

		:raises ChannelNotSupportedException: the device doesn't support K-Line
		'''
		raise ChannelNotSupportedException('{} does not support K-Line'.format(type(self).__name__))

	def canbus (
		self,
		bitrate: int = 500_000,
		filters: list[CanFilter] | None = None,
	) -> CanChannel:
		'''
		Get the CAN bus channel of this device. Opens the device (not the channel) if it wasn't
		open. The channel isn't opened - open it yourself, or let the transport do it

		:raises ChannelNotSupportedException: the device doesn't support CAN bus
		'''
		raise ChannelNotSupportedException(
			'{} does not support CAN bus'.format(type(self).__name__)
		)

	@abstractmethod
	def description (self) -> str:
		'''
		Human readable description, e.g. for listing devices in a UI
		'''

	@classmethod
	@abstractmethod
	def discover (cls) -> list[Self]:
		'''
		Find connected devices of this type. Nothing is opened

		:return: unopened device instances
		'''

	@classmethod
	def from_port (cls, port: str) -> Self | None:
		'''
		Create the device from a port string, the way discovered devices identify themselves
		(e.g. /dev/ttyUSB0, can0, pcan:PCAN_USBBUS1). Nothing is opened

		:return: None if the port isn't one of this device type
		'''
		return None

	def _hand_out (self, bus: Bus, create: Callable[[], T]) -> T:
		'''
		Open the device (not the channel) if it wasn't open, create the channel for the bus
		and keep track of it, so close() can shut it down later. The channel is not opened

		:param create: creates the channel, called only if it can be handed out
		:raises ChannelInUseException: the channel handed out earlier for this bus is still open
		'''
		current = self._channels.get(bus)
		if current is not None and current.is_open():
			raise ChannelInUseException(
				'{} on {} is already open'.format(bus.value, self.description())
			)
		if not self.is_open():
			self.open()

		channel = create()
		self._channels[bus] = channel
		return channel

	def __enter__ (self) -> Self:
		self.open()
		return self

	def __exit__ (self, *exc_info: object) -> None:
		self.close()
