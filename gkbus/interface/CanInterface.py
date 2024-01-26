from scapy.config import conf
conf.contribs['CANSocket'] = {'use-python-can': False}
conf.contribs['ISOTP'] = {'use-can-isotp-kernel-module': True}
from scapy.contrib.cansocket import *
from scapy.contrib.isotp import *
import logging
from .Interface import InterfaceABC
logger = logging.getLogger(__name__)

class CanInterface(InterfaceABC):
	socket = False

	def __init__ (self, rx_id: int, tx_id: int, interface: str = 'can0'):
		self.socket = ISOTPNativeSocket(iface=interface, tx_id=tx_id, rx_id=rx_id, padding=True)

	def _execute_internal (self, payload: list[int]) -> list[int]:
		response = self.socket.sr1(ISOTP(bytes(payload)), verbose=False)

		data = list(response.data)

		if (len(data) > 2):
			if (data[0] == 0x7f and data[2] == 0x78): # request received response pending
				logger.warning('ECU is busy, request received, response pending.')
				response = self.socket.recv()
				return list(response.data)
		return data 

	def set_timeout (self, timeout: int | None = None):
		if (timeout == None):
			self.socket.timeout = 5
		else:
			self.socket.timeout = timeout
		return self
		
	def shutdown (self) -> None:
		self.socket.close()
		super().shutdown()