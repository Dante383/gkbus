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
		Open the transport (and the channel, if it isn't open yet) - get ready to interact.
		Does nothing if the transport is already open
		'''
		return self.transport.open()

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
		Close the transport, and the channel if the transport opened it.
		Does nothing if the transport is already closed
		'''
		self.transport.close()

	def set_transport (self, transport: TransportABC) -> Self:
		'''
		Replace transport used by the protocol instance. 
		Remember to close the previous socket first, 
		this won't happen automatically

		:param transport: Transport instance to replace current one with
		'''
		self.transport = transport