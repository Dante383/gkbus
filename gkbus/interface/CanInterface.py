from scapy.config import conf
conf.contribs['CANSocket'] = {'use-python-can': False}
conf.contribs['ISOTP'] = {'use-can-isotp-kernel-module': True}
from scapy.contrib.cansocket import *
from scapy.contrib.isotp import *
from ..kwp.KWPResponse import KWPResponse
from .Interface import InterfaceABC

class CanInterface(InterfaceABC):
	socket = False

	def __init__ (self, rx_id, tx_id, interface='can0'):
		self.socket = ISOTPNativeSocket(iface=interface, tx_id=tx_id, rx_id=rx_id, padding=True)

	def _execute_internal (self, kwp_command):
		data = [kwp_command.command] + kwp_command.data
 
		response = self.socket.sr1(ISOTP(bytes(data)), verbose=False)

		response = list(response.data)
		return KWPResponse().set_status(response[0]).set_data(response[1:])
		
	def shutdown (self) -> None:
		self.socket.close()