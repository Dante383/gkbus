import os, math
from sys import platform
from typing_extensions import Self
from scapy.config import conf
conf.contribs['CANSocket'] = {'use-python-can': False}
from scapy.contrib.cansocket import CANSocket
from scapy.layers.can import CAN, CAN_MTU, CAN_MAX_DLEN
from scapy.error import Scapy_Exception
from .hardware_abc import HardwareABC, HardwarePort, OpeningPortException, SendingException, TimeoutException

CAN_HEADER_LEN = CAN_MTU-CAN_MAX_DLEN

class CanHardware(HardwareABC):
	'''
	Hardware class for CAN Bus interfaces. Uses Scapy as a backend
	'''

	def __init__ (self, port: str, tx_id: int = None, rx_id: int = None, timeout: int = 1) -> None:
		self.port = port
		self.tx_id, self.rx_id = tx_id, rx_id
		self.timeout = timeout

	def _build_filters (self) -> list[dict]:
		filters = []
		
		if self.rx_id:
			filters.append({'can_id': self.rx_id, 'can_mask': 0x7FF})
		else:
			filters = None

		return filters

	def open (self) -> bool:
		try:
			self.socket = CANSocket(channel=self.port, can_filters=self._build_filters())
		except (OSError, Scapy_Exception) as e:
			raise OpeningPortException(e)
		return True

	def read (self, length: int) -> bytes:
		try:
			packet = self.socket.sniff(timeout=self.timeout, count=1)[0]
		except IndexError:
			raise TimeoutException

		return packet.data

	def write (self, data: bytes, tx_id: int = None) -> int:
		tx_id = tx_id if tx_id != None else self.tx_id
		if tx_id == None:
			raise SendingException('Tried to send without CAN Bus ID specified')

		packet = CAN(identifier=tx_id, data=data)

		bytes_written = self.socket.send(packet)

		return bytes_written-CAN_HEADER_LEN

	def close (self) -> None:
		self.socket.close()

	def get_baudrate (self) -> int:
		raise NotImplementedError

	def set_baudrate (self, baudrate: int) -> Self:
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
		interfaces = []

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