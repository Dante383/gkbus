import logging
from typing import TYPE_CHECKING, Self

from ...channel import CanFilter, KLineTiming
from ...exceptions import ChannelException, ChannelNotSupportedException, DeviceException
from ..device_abc import Bus, DeviceABC
from ..obd_pin import ObdPin
from .constants import SHORT_TO_GROUND, VOLTAGE_OFF, Status
from .library import J2534Error, J2534Library
from .registry import J2534LibraryInfo, find_libraries, find_library

if TYPE_CHECKING:
	from .j2534_can_channel import J2534CanChannel
	from .j2534_kline_channel import J2534KLineChannel

logger = logging.getLogger(__name__)

#: port strings of J2534 devices start with this, e.g. j2534:openport
PORT_PREFIX = 'j2534'
#: why PassThruOpen fails, in words
OPENING_REASONS: dict[int, str] = {
	Status.ERR_DEVICE_NOT_CONNECTED: '{} is not connected',
	Status.ERR_DEVICE_IN_USE: '{} is in use by another program',
}
#: statuses of PassThruSetProgrammingVoltage that mean the adapter can't ground the pin. The
#: OpenPort takes grounding pin 2, which only does voltage, for a voltage out of range
CANT_GROUND = frozenset({
	Status.ERR_PIN_INVALID,
	Status.ERR_NOT_SUPPORTED,
	Status.ERR_OEM_VOLTAGE_TOO_HIGH,
	Status.ERR_OEM_VOLTAGE_TOO_LOW,
})

class J2534Device(DeviceABC):
	'''
	SAE J2534 pass-thru adapter (Tactrix OpenPort 2.0 and others), driven through its
	J2534 library - Tactrix's DLL on Windows, openport-j2534 on Linux and macOS.

	The library is loaded and the adapter taken (PassThruOpen) when the device is opened,
	never by discover(). J2534 allows one program to use an adapter at a time.

	Pins are grounded with PassThruSetProgrammingVoltage. Which pins K-Line can be switched to
	and which can be grounded is known for some adapters (see registry.py); J2534 only
	guarantees K-Line on pin 7 and grounding pin 15. An adapter that acknowledges grounding
	a pin it can't actually ground (OpenPort clones) can't be told apart
	'''

	buses = frozenset({Bus.KLINE, Bus.CANBUS})

	def __init__ (self, library: J2534LibraryInfo | str | None = None) -> None:
		'''
		:param library: the J2534 library to use, a path to one, or a part of an installed
			library's name or vendor (e.g. openport). None - the first installed library
		:raises DeviceException: no such library is installed
		'''
		super().__init__()
		if not isinstance(library, J2534LibraryInfo):
			info = find_library(library)
			if info is None:
				raise DeviceException(
					'No J2534 library {}installed'.format(
						'matching {} is '.format(library) if library else 'is '
					)
				)
			library = info
		self.library = library
		self.profile = library.profile
		#: narrowed to what the library declared
		self.buses = library.buses
		self.port = '{}:{}'.format(PORT_PREFIX, library.name)
		#: reported by the adapter when it's opened
		self.firmware_version: str | None = None
		self.library_version: str | None = None
		self.api_version: str | None = None
		self._library: J2534Library | None = None
		self._device_id: int | None = None

	def open (self) -> bool:
		'''
		Load the library and take the adapter. Does nothing if the device is already open

		:raises OpeningChannelException: the library couldn't be loaded, the adapter isn't
			connected or another program uses it
		'''
		if self._opened:
			return True
		library = J2534Library(self.library.path)
		try:
			device_id = library.open()
		except J2534Error as e:
			raise self._opening_error(e) from e
		self._library, self._device_id = library, device_id
		self._opened = True

		try:
			self.firmware_version, self.library_version, self.api_version = \
				library.read_version(device_id)
		except J2534Error as e:
			logger.debug('Reading the versions of {} failed: {}'.format(self.library.name, e))
		logger.debug('Opened {}: firmware {}, library {}, API {}'.format(
			self.library.name, self.firmware_version, self.library_version, self.api_version
		))
		return True

	def close (self) -> None:
		'''
		Close the channels it handed out, release the pins it grounded and the adapter.
		Does nothing if the device is already closed
		'''
		try:
			super().close()
		finally:
			library, device_id = self._library, self._device_id
			self._library = self._device_id = None
			if library is not None and device_id is not None:
				try:
					library.close(device_id)
				except J2534Error as e:
					logger.warning('Closing {} failed: {}'.format(self.library.name, e))

	def kline (
		self,
		baudrate: int = 10400,
		pin: ObdPin = ObdPin.K_LINE,
		timing: KLineTiming | None = None,
	) -> 'J2534KLineChannel':
		'''
		Get the K-Line channel. Opens the device (not the channel) if it wasn't open.
		The channel isn't opened - open it yourself, or let the transport do it.
		The adapter keeps to the timing itself

		:param pin: OBD pin to do K-Line on. Whether the adapter can is found out when the
			channel is opened, which raises ChannelNotSupportedException if it can't
		:raises ChannelNotSupportedException: the library doesn't do K-Line
		:raises ChannelInUseException: the K-Line channel handed out earlier is still open
		:raises ValueError: the pin is ground or battery
		:raises DeviceException: the pin is grounded
		'''
		from .j2534_kline_channel import J2534KLineChannel

		self._require(Bus.KLINE)
		pin = self._obd_pin(pin)
		return self._hand_out(
			Bus.KLINE,
			lambda: J2534KLineChannel(self, baudrate=baudrate, pin=pin, timing=timing),
			pins=frozenset({pin}),
		)

	def kline_pins (self) -> frozenset[ObdPin]:
		'''
		Pins the adapter is known to do K-Line on. Others may work too, if it supports
		J2534-2 pin switching
		'''
		return self.profile.kline_pins if Bus.KLINE in self.buses else frozenset()

	def groundable_pins (self) -> frozenset[ObdPin]:
		return self.profile.groundable_pins

	def canbus (
		self,
		bitrate: int = 500_000,
		filters: list[CanFilter] | None = None,
	) -> 'J2534CanChannel':
		'''
		Get the CAN bus channel. Opens the device (not the channel) if it wasn't open.
		The channel isn't opened - open it yourself, or let the transport do it.
		ISO-TP links from it are done by the adapter

		:raises ChannelNotSupportedException: the library doesn't do CAN
		:raises ChannelInUseException: the CAN bus channel handed out earlier is still open
		'''
		from .j2534_can_channel import J2534CanChannel

		self._require(Bus.CANBUS)
		return self._hand_out(
			Bus.CANBUS, lambda: J2534CanChannel(self, bitrate=bitrate, filters=filters),
		)

	def battery_voltage (self) -> float:
		'''
		Voltage on OBD pin 16 (battery positive), in volts. Opens the device if it wasn't open
		'''
		library, device_id = self.handle()
		return library.read_vbatt(device_id) / 1000

	def handle (self) -> tuple[J2534Library, int]:
		'''
		The loaded library and the J2534 device id, for channels to call it with.
		Opens the device if it wasn't open
		'''
		if not self._opened:
			self.open()
		if self._library is None or self._device_id is None:
			raise ChannelException('{} is not open'.format(self.description()))
		return self._library, self._device_id

	def description (self) -> str:
		text = 'J2534 {}'.format(self.library.name)
		if self.library.vendor:
			text += ' ({})'.format(self.library.vendor)
		if self.firmware_version:
			text += ', firmware {}'.format(self.firmware_version)
		return text

	@classmethod
	def discover (cls) -> list[Self]:
		'''
		Installed J2534 libraries whose adapter is plugged in, or might be - most libraries
		can't tell without taking the adapter, which discovery never does
		'''
		devices = []
		for library in find_libraries():
			if library.present() is False:
				continue
			if not library.loadable():
				logger.warning(
					'Skipping J2534 library {}: it is {}, this Python can\'t load it'.format(
						library.path, library.machine
					)
				)
				continue
			devices.append(cls(library))
		return devices

	@classmethod
	def from_port (cls, port: str) -> Self | None:
		'''
		Recognises j2534 (the first installed library), j2534:<part of a library's name or
		vendor> (e.g. j2534:openport) and j2534:<path to a library>

		:raises DeviceException: no such library is installed
		'''
		prefix, _, spec = port.partition(':')
		if prefix.lower() != PORT_PREFIX:
			return None
		return cls(spec or None)

	def _ground (self, pin: ObdPin) -> bool:
		'''
		:raises DeviceException: a channel uses the pin
		'''
		library, device_id = self.handle()
		try:
			library.set_programming_voltage(device_id, pin, SHORT_TO_GROUND)
		except J2534Error as e:
			if e.status in CANT_GROUND:
				logger.debug('Grounding {} on {} failed: {}'.format(pin, self.description(), e))
				return False
			if e.status == Status.ERR_CHANNEL_IN_USE:
				raise DeviceException('{} is used by an open channel of {}'.format(
					pin, self.description()
				)) from e
			raise
		return True

	def _release (self, pin: ObdPin) -> None:
		library, device_id = self.handle()
		library.set_programming_voltage(device_id, pin, VOLTAGE_OFF)

	def _require (self, bus: Bus) -> None:
		if bus not in self.buses:
			raise ChannelNotSupportedException(
				'{} does not support {}'.format(self.description(), bus.value)
			)

	def _opening_error (self, error: J2534Error) -> J2534Error:
		'''
		The same error, with the usual causes spelled out
		'''
		reason = OPENING_REASONS.get(error.status)
		if reason is None:
			return error
		description = reason.format(self.library.name)
		if error.description and not error._repeats(error.description):
			description += ' ({})'.format(error.description)
		return type(error)(error.function, error.status, description)
