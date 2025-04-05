import time
from sys import platform

from scapy.config import conf

if platform.startswith('win32'):
	conf.contribs['ISOTP'] = {'use-can-isotp-kernel-module': False}
else:
	conf.contribs['ISOTP'] = {'use-can-isotp-kernel-module': True}
from scapy.contrib.isotp import ISOTP, ISOTPSocket

from ..hardware.can_hardware import CanFilter
from ..hardware.hardware_abc import HardwareABC, TimeoutException
from .transport_abc import PacketDirection, RawPacket, TransportABC


class Kwp2000OverCanTransport (TransportABC):
	def __init__ (self, hardware: HardwareABC, tx_id: int, rx_id: int) -> None:
		self.hardware = hardware
		self.tx_id, self.rx_id = tx_id, rx_id
		self.isotp: ISOTPSocket | None = None

	def init (self) -> bool:
		self.hardware.set_filters([CanFilter(can_id=self.rx_id, can_mask=0x7ff)])
		
		if not self.hardware.port_opened:
			self.hardware.open()

		if not self.isotp:
			self.isotp = ISOTPSocket(self.hardware.socket, self.tx_id, self.rx_id, padding=True)

		return True
		
	def send_pdu (self, pdu: bytes) -> int:
		data = pdu
		bytes_written = self.isotp.send(data)

		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))

		return len(data) # isotp socket doesnt return how many bytes were written

	def read_pdu (self) -> bytes:
		try:
			frame = self.isotp.sniff(timeout=self.hardware.get_timeout(), count=1)[0]
		except IndexError:
			self.isotp.close() # close the background thread that sends flow control frames
			raise TimeoutException

		self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=frame.data, timestamp=int(time.time() * 1000)))

		return frame.data

	def send_read_pdu (self, data: bytes) -> bytes:
		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))
		response = self.isotp.sr1(ISOTP(bytes(data)), verbose=False)

		if not response:
			raise TimeoutException

		self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=response.data, timestamp=int(time.time() * 1000)))

		return response.data