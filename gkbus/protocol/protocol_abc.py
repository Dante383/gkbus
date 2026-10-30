from abc import ABC

from typing import Self

from ..transport.transport_abc import TransportABC


class ProtocolException(IOError):
	pass

class ProtocolABC (ABC):
	def __init__ (self, transport: TransportABC) -> None:
		self.transport = transport

	def open (self) -> bool:
		'''
		Initialize hardware/transport layers - get ready to interact.
		Does nothing if the transport is already open
		'''
		if not self.transport.is_open():
			return self.transport.open()

		return True

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
		Shutdown the underlaying layers. Does nothing if the transport is already closed
		'''
		if self.transport.is_open():
			self.transport.close()

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