import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Self, TypeVar

from ..channel import CanChannel, CanFilter, ChannelABC, KLineChannel, KLineTiming
from ..exceptions import (
	ChannelInUseException,
	ChannelNotSupportedException,
	DeviceException,
	GkbusException,
)
from .obd_pin import POWER_PINS, ObdPin

T = TypeVar('T', bound=ChannelABC)

logger = logging.getLogger(__name__)


class Bus(Enum):
	KLINE = 'kline'
	CANBUS = 'canbus'

#: OBD pins each bus uses, unless the device was asked for others
BUS_PINS: dict[Bus, frozenset[ObdPin]] = {
	Bus.KLINE: frozenset({ObdPin.K_LINE}),
	Bus.CANBUS: frozenset({ObdPin.CAN_HIGH, ObdPin.CAN_LOW}),
}

class DeviceABC(ABC):
	'''
	Abstract device class. Device refers to the actual physical device you're using for
	communication, reached through one particular access method (serial port, J2534 library,
	SocketCAN, ...). A device hands out a channel for every bus it supports. J2534 would hand out
	K-Line and CAN bus channels, SerialKLineDevice only a K-Line channel, etc.

	Creating a device doesn't open anything, so instances returned by discover()
	are safe to list and discard.

	Devices that can't switch K-Line to another OBD pin or ground pins themselves still accept
	the requests - they log what the user has to wire instead, see kline() and ground_pin()
	'''

	#: buses this device type can provide channels for
	buses: frozenset[Bus] = frozenset()

	def __init__ (self) -> None:
		self._opened = False
		self._channels: dict[Bus, ChannelABC] = {}
		#: OBD pins of the channels handed out
		self._channel_pins: dict[Bus, frozenset[ObdPin]] = {}
		#: grounded pins: True - the device holds them to ground, False - the user was asked to
		self._grounded: dict[ObdPin, bool] = {}

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
		Close the device and any channels it handed out, and release the pins it grounded.
		Does nothing if the device is already closed
		'''
		try:
			for channel in self._channels.values():
				if channel.is_open():
					channel.close()
		finally:
			self._channels.clear()
			self._channel_pins.clear()
			for pin in list(self._grounded):
				try:
					self.release_pin(pin)
				except GkbusException as e:
					logger.warning('Releasing {} failed: {}'.format(pin, e))
			self._grounded.clear()
			self._opened = False

	def kline (
		self,
		baudrate: int = 10400,
		pin: ObdPin = ObdPin.K_LINE,
		timing: KLineTiming | None = None,
	) -> KLineChannel:
		'''
		Get the K-Line channel of this device. Opens the device (not the channel) if it wasn't open.
		The channel isn't opened - open it yourself, or let the transport do it

		:param pin: OBD pin to do K-Line on. Devices that can't switch pins (see kline_pins())
			log which pin their K-Line has to be wired to and carry on
		:param timing: ISO 14230 bus timing, for devices that time the bus themselves.
			ISO 14230 defaults if not provided

		:raises ChannelNotSupportedException: the device doesn't support K-Line
		:raises ValueError: the pin is ground or battery
		:raises DeviceException: the pin is grounded
		'''
		raise ChannelNotSupportedException('{} does not support K-Line'.format(type(self).__name__))

	def kline_pins (self) -> frozenset[ObdPin]:
		'''
		OBD pins this device can switch its K-Line to. Empty - the wiring is fixed, the user has to
		connect it to the pin passed to kline()
		'''
		return frozenset()

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

	def groundable_pins (self) -> frozenset[ObdPin]:
		'''
		OBD pins this device is known to be able to short to ground. Advisory - ground_pin() tries
		any pin. Empty - the user has to ground them
		'''
		return frozenset()

	@property
	def grounded_pins (self) -> frozenset[ObdPin]:
		'''
		Pins the device itself holds to ground
		'''
		return frozenset(pin for pin, held in self._grounded.items() if held)

	def ground_pin (self, pin: ObdPin) -> bool:
		'''
		Short an OBD pin to ground, e.g. to put an ECU into boot mode. Several pins can be
		grounded at once. Opens the device if it wasn't open. Does nothing if the pin is
		grounded already

		:return: True - the device grounded it. False - it can't, so a warning asking the user
			to connect the pin to ground was logged; apps may want to show their own prompt
		:raises ValueError: the pin is ground or battery
		:raises DeviceException: an open channel of this device uses the pin
		'''
		pin = self._obd_pin(pin)
		if pin in self._grounded:
			return self._grounded[pin]
		for bus, pins in self._channel_pins.items():
			if pin in pins and self._channels[bus].is_open():
				raise DeviceException('{} is used by the open {} channel of {}'.format(
					pin, bus.value, self.description()
				))
		if not self.is_open():
			self.open()

		held = self._ground(pin)
		if not held:
			logger.warning('Connect {} to ground: {} can\'t ground it'.format(
				pin, self.description()
			))
		self._grounded[pin] = held
		return held

	def release_pin (self, pin: ObdPin) -> None:
		'''
		Undo ground_pin(). Does nothing for pins that aren't grounded
		'''
		pin = ObdPin(pin)
		held = self._grounded.get(pin)
		if held is None:
			return
		if held:
			self._release(pin)
		else:
			logger.warning('{} can be disconnected from ground'.format(pin))
		del self._grounded[pin]

	@contextmanager
	def grounded (self, *pins: ObdPin) -> Iterator[frozenset[ObdPin]]:
		'''
		Ground the pins for the duration of the with block, see ground_pin(). Pins that were
		grounded before stay grounded after it

		:return: the pins the user has to ground, the device couldn't
		'''
		grounded = []
		try:
			for pin in pins:
				pin = self._obd_pin(pin)
				if pin not in self._grounded:
					self.ground_pin(pin)
					grounded.append(pin)
			yield frozenset(pin for pin in pins if not self._grounded[ObdPin(pin)])
		finally:
			for pin in reversed(grounded):
				self.release_pin(pin)

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

	def _hand_out (
		self,
		bus: Bus,
		create: Callable[[], T],
		pins: frozenset[ObdPin] | None = None,
	) -> T:
		'''
		Open the device (not the channel) if it wasn't open, create the channel for the bus
		and keep track of it, so close() can shut it down later. The channel is not opened

		:param create: creates the channel, called only if it can be handed out
		:param pins: OBD pins the channel uses, the bus' usual ones if not provided
		:raises ChannelInUseException: the channel handed out earlier for this bus is still open
		:raises DeviceException: one of the pins is grounded
		'''
		pins = BUS_PINS[bus] if pins is None else pins
		current = self._channels.get(bus)
		if current is not None and current.is_open():
			raise ChannelInUseException(
				'{} on {} is already open'.format(bus.value, self.description())
			)
		for pin in sorted(pins):
			if pin in self._grounded:
				raise DeviceException('{} is grounded, release it before using it for {}'.format(
					pin, bus.value
				))
		if not self.is_open():
			self.open()

		channel = create()
		self._channels[bus] = channel
		self._channel_pins[bus] = pins
		return channel

	def _ground (self, pin: ObdPin) -> bool:
		'''
		Short the pin to ground, if the device can. The device is open

		:return: False if it can't
		'''
		return False

	def _release (self, pin: ObdPin) -> None:
		'''
		Let go of a pin _ground() grounded
		'''

	@staticmethod
	def _obd_pin (pin: ObdPin | int) -> ObdPin:
		'''
		:raises ValueError: not an OBD pin, or one that's ground or battery
		'''
		pin = ObdPin(pin)
		if pin in POWER_PINS:
			raise ValueError('{} is {}'.format(
				pin, 'battery positive' if pin == ObdPin.BATTERY else 'ground'
			))
		return pin

	def __enter__ (self) -> Self:
		self.open()
		return self

	def __exit__ (self, *exc_info: object) -> None:
		self.close()
