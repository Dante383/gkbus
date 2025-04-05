import time

from ..hardware.can_hardware import CanFilter
from ..hardware.hardware_abc import HardwareABC, RawFrame
from .transport_abc import PacketDirection, RawPacket, TransportABC


class CcpOverCanTransport (TransportABC):
	'''
	CAN Calibration Protocol transport. 
	Nothing interesting here - CCP doesn't use ISOTP or any other way to break 
	chunks of data into messages - each command or response must fit within 8 bytes of
	a standard CAN frame
	'''
	def __init__ (self, hardware: HardwareABC, tx_id: int, rx_id: int) -> None:
		self.hardware = hardware
		self.tx_id, self.rx_id = tx_id, rx_id
		self.hardware.set_filters([CanFilter(can_id=self.rx_id, can_mask=0x7ff)])
		
	def send_pdu (self, pdu: bytes) -> int:
		data = pdu
		bytes_written = self.hardware.write(RawFrame(identifier=self.tx_id, data=data))

		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))

		return len(data) # can socket doesnt return how many bytes were written @TODO: verify

	def read_pdu (self) -> bytes:
		frame = self.hardware.read(8).data

		self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=frame, timestamp=int(time.time() * 1000)))

		return frame