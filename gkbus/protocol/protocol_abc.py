from abc import ABC
from ..transport.transport_abc import TransportABC

class ProtocolABC (ABC):
	def __init__ (self, transport: TransportABC) -> None:
		self.transport = transport

	def open (self) -> bool:
		'''
		Initialize the underlaying layers - get ready to interact
		'''
		pass

	def close (self) -> None:
		'''
		Shutdown the underlaying layers
		'''
		pass

	def __del__ (self) -> None:
		self.close()