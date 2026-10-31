from sys import platform
from typing import Self

from ..hardware import CanFilter, CanHardware
from ..hardware.can_hardware import CAN_BACKEND_HARDWARE, CanBackend
from .device_abc import Bus, DeviceABC


class PythonCanDevice(DeviceABC):
	'''
	CAN adapter driven through python-can on Windows: PCAN, Vector, slcan (CANable) and GS-USB
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
		:raises ValueError: the port isn't a supported interface and channel
		'''
		super().__init__()
		interface, _, channel = port.partition(':')
		try:
			self._backend = CAN_BACKEND_HARDWARE[CanBackend(interface)]
		except ValueError as exc:
			raise ValueError('Unsupported CAN interface: {}'.format(port)) from exc
		if not channel:
			raise ValueError('No channel given for CAN interface: {}'.format(port))

		self.port = port
		self.manufacturer = manufacturer
		self.serial_number = serial_number

	def canbus (
		self,
		bitrate: int = 500_000,
		timeout: float = 1,
		filters: list[CanFilter] | None = None,
	) -> CanHardware:
		'''
		Get CAN bus hardware on this device. Opens the device (not the hardware) if it wasn't open.
		The hardware isn't opened - open it yourself, or let the transport do it

		:raises ChannelInUseException: CAN bus hardware handed out earlier is still open
		'''
		return self._hand_out(
			Bus.CANBUS,
			lambda: self._backend(self.port, bitrate=bitrate, timeout=timeout, filters=filters),
		)

	def description (self) -> str:
		details = ' '.join([x for x in [self.manufacturer, self.serial_number] if x])
		return '{} - {}'.format(self.port, details) if details else self.port

	@classmethod
	def discover (cls) -> list[Self]:
		if not platform.startswith('win32'):
			return []
		return [
			cls(port.port, manufacturer=port.manufacturer, serial_number=port.serial_number)
			for port in CanHardware.available_ports()
		]
