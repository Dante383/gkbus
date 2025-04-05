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
		return 'RawPacket({}, ts={}, data={!r})'.format(direction, self.timestamp, self.data)

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

	def __init__ (self, hardware: HardwareABC, tx_id: int | None = None, rx_id: int | None = None) -> None:
		'''
		TransportABC constructor

		:param hardware: HardwareABC instance
		:param tx_id: Default identifier to transmit on - optional, hardware specific
		:param rx_id: Default identifier to listen for - optional, hardware specific. 
			For CAN based transports, this will be set as filter in the interface
		'''
		self.hardware = hardware
		self.tx_id, self.rx_id = tx_id, rx_id
		self.buffer = []

	def init (self) -> bool:
		'''
		Get ready to transfer: initialize the underlaying hardware if not initialized already
		Calling this method is not required - it's just a helper to avoid manual hardware initialization
		'''
		if not self.hardware.port_opened:
			return self.hardware.open()
		return True

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

	def set_tx_id (self, tx_id: int) -> Self:
		'''
		Set default identifier to transmit on - hardware specific

		:param tx_id: Identifier to transmit on
		'''
		self.hardware.set_tx_id(tx_id)
		self.tx_id = tx_id

	def get_tx_id (self) -> int:
		'''
		Get default identifier to transmit on
		'''
		return self.tx_id

	def get_rx_id (self, rx_id: int) -> int:
		'''
		Get current identifier to listen for. Depending on the hardware,
		a hardware filter should be created with this identifier,
		meaning no other messages will be received or processed
		'''
		return self.rx_id

	def set_buffer_size (self, buffer_size: int) -> Self:
		'''
		Set size of the buffer. 

		:param buffer_size: 0 for unlimited, None for no logging
		:type buffer_size: int
		:rtype: TransportABC
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

		:return: A list of RawPacket objects
		'''
		packets = self.buffer
		self.buffer = []
		return packets