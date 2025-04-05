import struct, time
from sys import platform
from .transport_abc import TransportABC, RawPacket, PacketDirection
from ..hardware.hardware_abc import HardwareABC, TimeoutException


class CcpOverCanTransport (TransportABC):
	'''
	CAN Calibration Protocol transport. 
	Nothing interesting here - CCP doesn't use ISOTP or any other way to break 
	chunks of data into messages - each command or response must fit within 8 bytes of
	a standard CAN frame
	'''
	def __init__ (self, hardware: HardwareABC, tx_id: hex, rx_id: hex) -> None:
		self.hardware = hardware
		self.tx_id, self.rx_id = tx_id, rx_id
		self.hardware.tx_id, self.hardware.rx_id = tx_id, rx_id
		
	def send_pdu (self, pdu: bytes) -> int:
		data = pdu
		bytes_written = self.hardware.write(data)

		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))

		return len(data) # can socket doesnt return how many bytes were written @TODO: verify

	def read_pdu (self) -> bytes:
		frame = self.hardware.read(8)

		self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=frame.data, timestamp=int(time.time() * 1000)))

		return frame