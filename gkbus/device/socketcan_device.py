from sys import platform
from typing import Self

from ..hardware import CanFilter, CanHardware
from ..hardware.can_hardware import SocketCanHardware
from .device_abc import Bus, DeviceABC


class SocketCanDevice(DeviceABC):
	'''
	CAN adapter exposed by the Linux kernel as a SocketCAN network interface
	(PCAN-USB, CANable with candleLight firmware and the like).
	The interface is configured and brought up when the CAN hardware is opened
	'''

	buses = frozenset({Bus.CANBUS})

	def __init__ (self, port: str) -> None:
		'''
		:param port: network interface name, for example can0
		'''
		super().__init__()
		self.port = port

	def canbus (
		self,
		bitrate: int = 500_000,
		timeout: float = 1,
		filters: list[CanFilter] | None = None,
	) -> SocketCanHardware:
		'''
		Get CAN bus hardware on this device. Opens the device (not the hardware) if it wasn't open.
		The hardware isn't opened - open it yourself, or let the transport do it

		:raises ChannelInUseException: CAN bus hardware handed out earlier is still open
		'''
		return self._hand_out(
			Bus.CANBUS,
			lambda: SocketCanHardware(self.port, bitrate=bitrate, timeout=timeout, filters=filters),
		)

	def description (self) -> str:
		return self.port

	@classmethod
	def discover (cls) -> list[Self]:
		if not platform.startswith('linux'):
			return []
		return [cls(port.port) for port in CanHardware.available_ports()]
