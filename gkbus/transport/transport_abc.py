import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Self

from ..channel import ChannelABC


class PacketDirection(Enum):
	INCOMING = 0
	OUTGOING = 1

@dataclass
class RawPacket:
	'''
	Raw packet being sent over the channel

	:param direction: Direction of the packet - incoming/outgoing
	:type direction: PacketDirection
	:param data: Raw data being sent over the channel
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
	Transport layer for protocols: turns PDUs into whatever goes over the channel and back.

	The transport opens the channel if it isn't open yet, and then it's also the one closing it.
	A channel you opened yourself stays open when the transport closes - so one channel can be
	handed from one transport to the next (e.g. KWP2000 followed by CCP on the same CAN bus)

	:param buffer: Buffer storing last X packets, X determined by
		buffer_size
	:type buffer: list[RawPacket]
	:param buffer_size: Determines the size of the buffer.
		0 - unlimited buffer, None - no buffer
	:type buffer_size: int
	'''
	buffer_size: int | None = 20

	def __init__ (
		self,
		channel: ChannelABC,
		tx_id: int | None = None,
		rx_id: int | None = None,
		timeout: float = 1,
	) -> None:
		'''
		:param channel: channel to communicate over, e.g. from device.kline() or device.canbus()
		:param tx_id: identifier to transmit on - transport specific
		:param rx_id: identifier to listen for - transport specific
		:param timeout: seconds to wait for a response
		'''
		self.channel = channel
		self.tx_id, self.rx_id = tx_id, rx_id
		self.timeout = timeout
		self.buffer: list[RawPacket] = []
		self._opened = False
		self._owns_channel = False

	def open (self) -> bool:
		'''
		Open the channel if it isn't open yet and get the transport ready.
		Does nothing if the transport is already open

		:return: a boolean indicating whether it was opened successfully
		'''
		if self.is_open():
			return True
		if self._opened:
			# the channel was closed under us - start over
			self.close()

		if not self.channel.is_open():
			self.channel.open()
			self._owns_channel = True
		try:
			self._open_link()
		except BaseException:
			self._release_channel()
			raise
		self._opened = True
		return True

	def is_open (self) -> bool:
		return self._opened and self.channel.is_open()

	def close (self) -> None:
		'''
		Close the transport, and the channel if the transport opened it.
		Does nothing if the transport is already closed
		'''
		if not self._opened:
			return
		self._opened = False
		try:
			self._close_link()
		finally:
			self._release_channel()

	def init (self, init_pdu: bytes | None = None) -> bool:
		'''
		Get ready to transfer: open if not open already and perform any bus-specific
		wake-up (e.g. fast init on K-Line)

		:param init_pdu: optional PDU used by transports that need one to wake up the bus,
			ignored by the others
		'''
		return self.open()

	@abstractmethod
	def send_pdu (self, data: bytes) -> int:
		'''
		Send a compiled PDU over the channel

		:return: number of PDU bytes sent
		'''

	@abstractmethod
	def read_pdu (self, timeout: float | None = None) -> bytes:
		'''
		Read a PDU from the channel

		:param timeout: seconds to wait, the transport's timeout if not provided
		:raises TimeoutException: nothing arrived in time
		'''

	def send_read_pdu (self, data: bytes) -> bytes:
		'''
		Send PDU and read the response
		'''
		self.send_pdu(data)
		return self.read_pdu()

	def get_tx_id (self) -> int | None:
		'''
		Get default identifier to transmit on
		'''
		return self.tx_id

	def get_rx_id (self) -> int | None:
		'''
		Get identifier to listen for
		'''
		return self.rx_id

	def set_timeout (self, timeout: float) -> Self:
		'''
		Set how long to wait for a response, in seconds
		'''
		self.timeout = timeout
		return self

	def get_timeout (self) -> float:
		return self.timeout

	def set_buffer_size (self, buffer_size: int | None) -> Self:
		'''
		Set size of the buffer.

		:param buffer_size: 0 for unlimited, None for no logging
		:rtype: TransportABC
		'''
		self.buffer_size = buffer_size
		return self

	def get_buffer_size (self) -> int | None:
		return self.buffer_size

	def buffer_push (self, packet: RawPacket) -> Self:
		if (self.buffer_size is None):
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

	def _record (self, direction: PacketDirection, data: bytes) -> None:
		self.buffer_push(RawPacket(direction=direction, data=data, timestamp=int(time.time()*1000)))

	def _open_link (self) -> None:
		'''
		Hook for transport specific setup, called once the channel is open
		'''

	def _close_link (self) -> None:
		'''
		Hook undoing _open_link(), called before the channel is closed
		'''

	def _timeout (self, timeout: float | None) -> float:
		return self.timeout if timeout is None else timeout

	def _release_channel (self) -> None:
		if self._owns_channel:
			self._owns_channel = False
			if self.channel.is_open():
				self.channel.close()

	def __enter__ (self) -> Self:
		self.open()
		return self

	def __exit__ (self, *exc_info: object) -> None:
		self.close()
