import time

from ..hardware.can_hardware import CanFilter
from ..hardware.hardware_abc import HardwareABC, RawFrame, TimeoutException
from .transport_abc import PacketDirection, RawPacket, TransportABC


class CcpOverCanTransport (TransportABC):
	'''
	CAN Calibration Protocol transport. 
	Nothing interesting here - CCP doesn't use ISOTP or any other way to break 
	chunks of data into messages - each command or response must fit within 8 bytes of
	a standard CAN frame
	'''
	def __init__ (self, hardware: HardwareABC, tx_id: int, rx_id: int, crm_only: bool = False) -> None:
		self.hardware = hardware
		self.tx_id, self.rx_id = tx_id, rx_id
		self.crm_only = crm_only
		self.hardware.set_filters([CanFilter(can_id=self.rx_id, can_mask=0x7ff)])
		
	def send_pdu (self, pdu: bytes) -> int:
		data = pdu
		bytes_written = self.hardware.write(RawFrame(identifier=self.tx_id, data=data))

		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))

		return len(data) # can socket doesnt return how many bytes were written @TODO: verify

	def read_pdu(self) -> bytes:

		start = time.time()

		while True:

			if (time.time() - start) > self.hardware.get_timeout():
				raise TimeoutException

			frame = self.hardware.read(8)

			if frame is None:
				continue

			data = frame.data

			if data is None:
				continue

			data = bytes(data)

			# Flashing mode:
			# accept CRM packets only
			if self.crm_only:

				if frame.identifier != self.rx_id:
					continue

				if len(data) < 3:
					continue

				if data[0] != 0xFF:
					continue

			self.buffer_push(
				RawPacket(
					direction=PacketDirection.INCOMING,
					data=data,
					timestamp=int(time.time() * 1000)
				)
			)

			return data
