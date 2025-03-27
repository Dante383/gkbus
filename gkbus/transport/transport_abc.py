from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing_extensions import Self
from ..hardware.hardware_abc import HardwareABC

class PacketDirection(Enum):
	INCOMING = 0
	OUTGOING = 1

@dataclass
class RawPacket:
	'''
	Raw packet being sent over the hardware port

	:param direction: Direction of the packet - incoming/outgoing
	:type direction: PacketDirection
	:param data: Raw data being sent over the hardware port
	:type data: bytes
	:param timestamp: Timestamp in miliseconds
	:type timestamp: int
	'''

	direction: PacketDirection
	data: bytes
	timestamp: int

	def __str__ (self) -> str:
		direction = 'Incoming' if self.direction == PacketDirection.INCOMING else 'Outgoing'
		return 'RawPacket({}, ts={}, data={})'.format(direction, self.timestamp, self.data)

	def __repr__ (self) -> str:
		return self.__str__()

class TransportABC(ABC):
	'''
	Transport layer for protocols

	:param buffer: Buffer storing last X packets, X determined by 
		buffer_size
	:type buffer: list[RawPacket]
	:param buffer_size: Determines the size of the buffer.
		0 - unlimited buffer, None - no buffer
	:type buffer_size: int
	'''
	buffer: list[RawPacket] = [] # is this shared between all transports? @todo critical
	buffer_size: int = 20

	def __init__ (self, hardware: HardwareABC) -> None:
		self.hardware = hardware
		self.buffer = []

	def send_pdu (self, data: bytes) -> int:
		'''
		Send a compiled PDU over hardware port
		'''
		pass

	def read_pdu (self) -> bytes:
		'''
		Read a PDU over hardware port
		'''
		pass

	def send_read_pdu (self, data: bytes) -> bytes:
		'''
		Send PDU and read the response
		'''
		self.send_pdu(data)
		return self.read_pdu()

	def set_buffer_size (self, buffer_size: int) -> Self:
		'''
		Set size of the buffer. 

		:param buffer_size: 0 for unlimited, None for no logging
		:type buffer_size: int
		'''
		self.buffer_size = buffer_size

	def get_buffer_size (self) -> int:
		return self.buffer_size

	def buffer_push (self, packet: RawPacket) -> Self:
		if (self.buffer_size == None):
			return self

		self.buffer.append(packet)
		if (self.buffer_size != 0 and len(self.buffer) > self.buffer_size):
			del self.buffer[0:(len(self.buffer)-self.buffer_size)]
		
		return self

	def buffer_dump (self) -> list[RawPacket]:
		'''
		Retrieve contents of the buffer and empty the buffer
		'''
		packets = self.buffer
		self.buffer = []
		return packets