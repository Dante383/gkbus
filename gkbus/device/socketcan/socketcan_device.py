import os
from sys import platform
from typing import Self

from ...channel import CanFilter
from ..device_abc import Bus, DeviceABC
from .socketcan_channel import SocketCanChannel

NET_DIR = '/sys/class/net'
#: ARPHRD_CAN
CAN_LINK_TYPE = '280'

class SocketCanDevice(DeviceABC):
	'''
	CAN adapter exposed by the Linux kernel as a SocketCAN network interface
	(PCAN-USB, CANable with candleLight firmware and the like).
	The interface is configured and brought up when the CAN bus channel is opened
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
		filters: list[CanFilter] | None = None,
	) -> SocketCanChannel:
		'''
		Get the CAN bus channel. Opens the device (not the channel) if it wasn't open.
		The channel isn't opened - open it yourself, or let the transport do it

		:raises ChannelInUseException: the CAN bus channel handed out earlier is still open
		'''
		return self._hand_out(
			Bus.CANBUS,
			lambda: SocketCanChannel(self.port, bitrate=bitrate, filters=filters),
		)

	def description (self) -> str:
		return self.port

	@classmethod
	def discover (cls) -> list[Self]:
		if not platform.startswith('linux') or not os.path.isdir(NET_DIR):
			return []
		return [cls(name) for name in sorted(os.listdir(NET_DIR)) if cls._is_can_interface(name)]

	@classmethod
	def from_port (cls, port: str) -> Self | None:
		'''
		Recognises names of existing SocketCAN interfaces
		'''
		if not platform.startswith('linux') or not cls._is_can_interface(port):
			return None
		return cls(port)

	@staticmethod
	def _is_can_interface (name: str) -> bool:
		if not name or '/' in name or name in ('.', '..'):
			return False
		try:
			with open(os.path.join(NET_DIR, name, 'type'), encoding='ascii') as handle:
				return handle.read().strip() == CAN_LINK_TYPE
		except OSError:
			return False
