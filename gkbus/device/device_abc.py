from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
from typing import Self, TypeVar

from ..hardware import CanFilter, CanHardware, HardwareABC, KLineHardware
from .device_exceptions import ChannelInUseException, ChannelNotSupportedException

T = TypeVar('T', bound=HardwareABC)


class Bus(Enum):
	KLINE = 'kline'
	CANBUS = 'canbus'

class DeviceABC(ABC):
	'''
	Abstract device class. Device refers to the actual physical device you're using for
	communication, reached through one particular access method (serial port, J2534 library,
	SocketCAN, ...). A device hands out Hardware for every bus it supports. J2534 would support
	KLineHardware and CanHardware, SerialKLineDevice only supports KLineHardware, etc.

	Creating a device doesn't open anything, so instances returned by discover()
	are safe to list and discard.
	'''

	#: buses this device type can provide hardware for
	buses: frozenset[Bus] = frozenset()

	def __init__ (self) -> None:
		self._opened = False
		self._hardware: dict[Bus, HardwareABC] = {}

	def open (self) -> bool:
		'''
		Open the device, so hardware can be requested from it.
		Does nothing if the device is already open
		'''
		self._opened = True
		return True

	def is_open (self) -> bool:
		return self._opened

	def close (self) -> None:
		'''
		Close the device and any hardware it handed out.
		Does nothing if the device is already closed
		'''
		for hardware in self._hardware.values():
			if hardware.is_open():
				hardware.close()
		self._hardware.clear()
		self._opened = False

	def kline (self, baudrate: int = 10400, timeout: float = 2) -> KLineHardware:
		'''
		Get K-Line hardware on this device. Opens the device (not the hardware) if it wasn't open.
		The hardware isn't opened - open it yourself, or let the transport do it

		:raises ChannelNotSupportedException: the device doesn't support K-Line
		'''
		raise ChannelNotSupportedException('{} does not support K-Line'.format(type(self).__name__))

	def canbus (
		self,
		bitrate: int = 500_000,
		timeout: float = 1,
		filters: list[CanFilter] | None = None,
	) -> CanHardware:
		'''
		Get CAN bus hardware on this device. Opens the device (not the hardware) if it wasn't open.
		The hardware isn't opened - open it yourself, or let the transport do it

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

	def _hand_out (self, bus: Bus, create: Callable[[], T]) -> T:
		'''
		Open the device (not the hardware) if it wasn't open, create hardware for the bus
		and keep track of it, so close() can shut it down later. The hardware is not opened

		:param create: creates the hardware, called only if it can be handed out
		:raises ChannelInUseException: hardware handed out earlier for this bus is still open
		'''
		current = self._hardware.get(bus)
		if current is not None and current.is_open():
			raise ChannelInUseException(
				'{} on {} is already open'.format(bus.value, self.description())
			)
		if not self.is_open():
			self.open()

		hardware = create()
		self._hardware[bus] = hardware
		return hardware

	def __enter__ (self) -> Self:
		self.open()
		return self

	def __exit__ (self, *exc_info: object) -> None:
		self.close()
