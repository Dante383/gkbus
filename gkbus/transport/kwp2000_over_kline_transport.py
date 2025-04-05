import logging
import time

from ..hardware.hardware_abc import HardwareABC, RawFrame
from .transport_abc import PacketDirection, RawPacket, TransportABC

logger = logging.getLogger(__name__)

class Kwp2000OverKLineTransport (TransportABC):
	def __init__ (self, hardware: HardwareABC, tx_id: int, rx_id: int) -> None:
		self.hardware: HardwareABC = hardware
		self.tx_id, self.rx_id = tx_id, rx_id

	def send_pdu (self, pdu: bytes) -> int:
		data = self.build_payload(pdu)

		bytes_written = self._write(data)
		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))

		return bytes_written

	def read_pdu (self) -> bytes:
		frame = bytes()
		data = bytes()

		frame += self._read(4)

		counter = frame[0]
		tx_rx_id = frame[1:3]

		if (counter == 0x80): # more than 127 bytes incoming, counter overflowed. counter is gonna come after IDs
			counter = frame[3]+1
			logger.debug('More than 127 bytes incoming: {}'.format(counter))
		else:
			counter = counter-0x80
			data += frame[3:4] # frame[3] == python would automatically convert it to int. frame[3:3] == byte slice 

		data_and_checksum = self._read(counter)
		frame += data_and_checksum
		data += data_and_checksum[:-1] # last byte is the checksum

		self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=frame, timestamp=int(time.time() * 1000)))

		return data

	def _write (self, data: bytes) -> int:
		logger.debug('K-Line sending: {}'.format(' '.join([hex(x) for x in list(data)])))
		return self.hardware.write(RawFrame(identifier=0, data=data))

	def _read (self, length: int) -> bytes:
		logger.debug('K-Line trying to read {} bytes'.format(length))
		data = self.hardware.read(length).data
		logger.debug('K-Line success: {}'.format(' '.join([hex(x) for x in list(data)])))
		return data

	def init (self, payload: bytes) -> tuple[bytes, int, int]:
		'''
		Bring up the socket if not opened already and initialize the K-Line by ISO14230. 
		'''
		if not self.hardware.port_opened:
			self.hardware.open()
		return self.hardware.iso14230_fast_init(self.build_payload(payload))

	def calculate_checksum (self, payload: bytes) -> int:
		return sum(payload) & 0xFF

	def build_payload (self, data: bytes) -> bytes:
		data_length = len(data)

		if (data_length < 127):
			counter = 0x80 + data_length
		else:
			counter = 0x80
			data = bytes([data_length]) + data

		payload = bytes([counter, self.tx_id, self.rx_id]) 
		payload += data
		payload += self.calculate_checksum(payload).to_bytes(1, 'big')

		return payload