import os
import time
from dataclasses import dataclass
from sys import platform

from scapy.config import conf
from typing_extensions import Self

if platform.startswith('win32'):
	conf.contribs['CANSocket'] = {'use-python-can': True}
else:
	conf.contribs['CANSocket'] = {'use-python-can': False}
	from scapy.contrib.cansocket import CANSocket
from scapy.error import Scapy_Exception
from scapy.layers.can import CAN, CAN_MAX_DLEN, CAN_MTU

from .hardware_abc import (
	HardwareABC,
	HardwarePort,
	OpeningPortException,
	RawFrame,
	TimeoutException,
)

CAN_HEADER_LEN = CAN_MTU-CAN_MAX_DLEN

@dataclass
class CanFilter:
	can_id: int
	can_mask: int = 0x7ff

class CanHardware(HardwareABC):
	'''
	Hardware class for CAN Bus interfaces. Uses Scapy as a backend

	:param filters: list of dictionaries containing hardware CAN filters.
		Keys: can_id, can_mask
	'''

	def __init__ (self, port: str, timeout: int = 1, filters: list[CanFilter] | None = None) -> None:
		self.port: str = port
		self.timeout: float = timeout
		self.port_opened: bool = False
		self.filters: list[CanFilter] = filters if filters != None else []

	def _build_filters (self) -> list[dict]:
		filters = []
		
		for can_filter in self.filters:
			filters.append({'can_id': can_filter.can_id, 'can_mask': can_filter.can_mask})

		if len(filters) == 0:
			filters = None

		return filters

	def open (self) -> bool:
		try:
			self.socket = CANSocket(channel=self.port, can_filters=self._build_filters())
			self.port_opened = True
		except (OSError, Scapy_Exception) as e:
			raise OpeningPortException(e)
		return True

	def read (self, length: int) -> RawFrame:
		try:
			packet = self.socket.sniff(timeout=self.timeout, count=1)[0]
		except IndexError:
			raise TimeoutException

		return RawFrame(identifier=packet.identifier, data=packet.data)

	def write (self, frame: RawFrame) -> int:
		packet = CAN(identifier=frame.identifier, data=frame.data)

		bytes_written = self.socket.send(packet)

		return bytes_written-CAN_HEADER_LEN

	def _read_with_software_filters (self, filters: list, timeout: float = 10.0) -> RawFrame:
		'''
		This should not be used and will be removed soon
		'''
		time_started = time.time()

		while True:
			packet = self.socket.recv()
			can_id = packet.identifier

			for can_filter in filters:
				if (can_id & can_filter['can_mask']) == (can_filter['can_id'] & can_filter['can_mask']):
					return RawFrame(identifier=packet.identifier, data=packet.data)

			if (time.time()-time_started) > timeout:
				raise TimeoutException

	def get_filters (self) -> list[CanFilter]:
		'''
		Get active hardware canbus id filters
		'''
		return self.filters

	def set_filters (self, filters: list[CanFilter]) -> Self:
		'''
		Replace hardware canbus id filters. 
		This will triger a restart of the socket
		'''
		self.filters = filters
		self.close()
		self.open()

	def add_filter (self, can_filter: CanFilter) -> Self:
		'''
		Add new hardware canbus id filter
		This will trigger a restart of the socket
		'''
		self.set_filters(self.get_filters() + can_filter)

	def close (self) -> None:
		if hasattr(self, 'socket'):
			self.socket.close()
		self.port_opened = False

	def set_baudrate (self, baudrate: int) -> Self:
		raise NotImplementedError

	def get_baudrate (self) -> int:
		raise NotImplementedError

	def set_timeout (self, timeout: float) -> Self:
		self.socket.timeout = timeout
		self.timeout = timeout
		return self

	@staticmethod
	def _available_ports_linux () -> list[str]:
		'''
		Returns a list of available CAN network interfaces by checking the /sys/class/net/<iface>/type file

		:return: a list containing interface identifiers (can0, vcan0, ...)
		'''
		NET_DIR = '/sys/class/net'
		interfaces: list[str] = []

		if not os.path.exists(NET_DIR):
			return interfaces

		for iface in os.listdir(NET_DIR):
			type_path = os.path.join(NET_DIR, iface, 'type')
			if os.path.isfile(type_path):
				with open(type_path, 'r') as f:
					iface_type = f.read().strip()

				if iface_type == '280':
					interfaces.append(iface)

		return interfaces

	@staticmethod
	def available_ports () -> list[HardwarePort]:
		if platform.startswith('win32'):
			return []
		else:
			ports = [HardwarePort(port=x, port_name=x) for x in CanHardware._available_ports_linux()]
		
		return ports
