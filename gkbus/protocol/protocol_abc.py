from abc import ABC

from typing_extensions import Self

from ..transport.transport_abc import TransportABC


class ProtocolException(IOError):
	pass

class ProtocolABC (ABC):
	def __init__ (self, transport: TransportABC) -> None:
		self.transport = transport

	def open (self) -> bool:
		'''
		Initialize hardware/transport layers - get ready to interact
		'''
		pass

	def init (self) -> bool:
		'''
		Initialize the protocol layer
		'''

	def execute (self, command):
		'''
		Execute a command and return the results
		'''
		pass

	def close (self) -> None:
		'''
		Shutdown the underlaying layers
		'''
		pass

	def set_transport (self, transport: TransportABC) -> Self:
		'''
		Replace transport used by the protocol instance. 
		Remember to close the previous socket first, 
		this won't happen automatically

		:param transport: Transport instance to replace current one with
		'''
		self.transport = transport

	def __del__ (self) -> None:
		self.close()