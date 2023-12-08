from scapy.config import conf
conf.contribs['CANSocket'] = {'use-python-can': False}
conf.contribs['ISOTP'] = {'use-can-isotp-kernel-module': True}
from scapy.contrib.cansocket import *
from scapy.contrib.isotp import *
from .Interface import InterfaceABC

class CanInterface(InterfaceABC):
	socket = False

	def __init__ (self, rx_id, tx_id, interface='can0'):
		self.socket = ISOTPNativeSocket(iface=interface, tx_id=tx_id, rx_id=rx_id, padding=True)

	def _execute_internal (self, payload):
		response = self.socket.sr1(ISOTP(bytes(payload)), verbose=False)

		return list(response.data)
		
	def shutdown (self) -> None:
		self.socket.close()