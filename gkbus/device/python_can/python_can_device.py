import logging
from sys import platform
from typing import Self

from can.interfaces import VALID_INTERFACES

from ...channel import CanFilter
from ..device_abc import Bus, DeviceABC
from .backends import BACKENDS
from .python_can_channel import PythonCanChannel

logger = logging.getLogger(__name__)

#: interfaces with a device of their own
EXCLUDED_INTERFACES = frozenset({'socketcan'})

class PythonCanDevice(DeviceABC):
	'''
	CAN adapter driven through python-can: PCAN, Vector, slcan (CANable), GS-USB or any other
	python-can interface. Adapters are only discovered on Windows - on Linux they show up
	as SocketCAN interfaces
	'''

	buses = frozenset({Bus.CANBUS})

	def __init__ (
		self,
		port: str,
		manufacturer: str | None = None,
		serial_number: str | None = None,
	) -> None:
		'''
		:param port: python-can interface and channel separated by a colon,
			for example pcan:PCAN_USBBUS1, vector:0, slcan:COM5 or gs_usb:0
		:raises ValueError: the port isn't a python-can interface and channel
		'''
		super().__init__()
		interface, channel = self._parse_port(port)
		if interface is None or channel is None:
			raise ValueError('Not a python-can interface and channel: {}'.format(port))

		self.port = port
		self.interface = interface
		self.channel = channel
		self.manufacturer = manufacturer
		self.serial_number = serial_number

	def canbus (
		self,
		bitrate: int = 500_000,
		filters: list[CanFilter] | None = None,
	) -> PythonCanChannel:
		'''
		Get the CAN bus channel. Opens the device (not the channel) if it wasn't open.
		The channel isn't opened - open it yourself, or let the transport do it

		:raises ChannelInUseException: the CAN bus channel handed out earlier is still open
		'''
		return self._hand_out(
			Bus.CANBUS,
			lambda: PythonCanChannel(
				self.interface, self.channel, bitrate=bitrate, filters=filters
			),
		)

	def description (self) -> str:
		details = ' '.join([x for x in [self.manufacturer, self.serial_number] if x])
		return '{} - {}'.format(self.port, details) if details else self.port

	@classmethod
	def discover (cls) -> list[Self]:
		if not platform.startswith('win32'):
			return []

		devices = []
		for interface, backend in BACKENDS.items():
			try:
				found = backend.discover()
			except Exception as e:
				logger.warning('Discovering {} adapters failed: {}'.format(interface, e))
				continue
			devices.extend(
				cls(
					'{}:{}'.format(interface, x.channel),
					manufacturer=x.manufacturer,
					serial_number=x.serial_number,
				)
				for x in found
			)
		return devices

	@classmethod
	def from_port (cls, port: str) -> Self | None:
		'''
		Recognises interface:channel, where interface is a python-can interface
		'''
		interface, channel = cls._parse_port(port)
		if interface is None or channel is None:
			return None
		return cls(port)

	@staticmethod
	def _parse_port (port: str) -> tuple[str | None, str | None]:
		interface, separator, channel = port.partition(':')
		if (not separator or not channel or channel.startswith('//')
			or interface not in VALID_INTERFACES or interface in EXCLUDED_INTERFACES):
			return None, None
		return interface, channel
