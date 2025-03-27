from abc import ABC
from ..transport.transport_abc import TransportABC

class ProtocolABC (ABC):
	def __init__ (self, transport: TransportABC) -> None:
		self.transport = transport