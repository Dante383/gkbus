import time
from sys import platform

from scapy.config import conf

if platform.startswith('win32'):
	import isotp
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
		self.isotp = None

	def init (self) -> bool:
		if self.isotp is not None and (not platform.startswith('win32') or self.isotp.started):
			return True
		self.hardware.set_filters([CanFilter(can_id=self.rx_id, can_mask=0x7ff)])
		
		if platform.startswith('win32'):
			# A caller may already have opened the Scapy socket; use a direct bus.
			if self.hardware.is_open():
				self.hardware.close()
			self.hardware.open(raw=True)
			try:
				mode = (isotp.AddressingMode.Normal_29bits if max(self.tx_id, self.rx_id) > 0x7ff
					else isotp.AddressingMode.Normal_11bits)
				self.isotp = isotp.CanStack(
					bus=self.hardware.socket,
					address=isotp.Address(mode, txid=self.tx_id, rxid=self.rx_id),
					params={"stmin": 0, "blocksize": 0, "tx_padding": 0xCC,
						"tx_data_min_length": 8, "blocking_send": True},
				)
				self.isotp.start()
				self.hardware._isotp_stack = self.isotp
			except Exception:
				self.isotp = None
				self.hardware.close()
				raise
		else:
			if not self.hardware.is_open():
				self.hardware.open()
			self.isotp = ISOTPSocket(self.hardware.socket, self.tx_id, self.rx_id, padding=True)

		return True
		
	def send_pdu (self, pdu: bytes) -> int:
		data = pdu
		if platform.startswith('win32'):
			try:
				self.isotp.send(data, send_timeout=self.hardware.get_timeout())
			except isotp.errors.BlockingSendTimeout as exc:
				raise TimeoutException from exc
		else:
			self.isotp.send(data)

		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))

		return len(data) # isotp socket doesnt return how many bytes were written

	def read_pdu (self) -> bytes:
		if platform.startswith('win32'):
			data = self.isotp.recv(block=True, timeout=self.hardware.get_timeout())
			if data is None:
				raise TimeoutException
			data = bytes(data)
			self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=data,
				timestamp=int(time.time() * 1000)))
			return data
		try:
			frame = self.isotp.sniff(timeout=self.hardware.get_timeout(), count=1)[0]
		except IndexError:
			self.isotp.close() # close the background thread that sends flow control frames
			raise TimeoutException

		self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=frame.data, timestamp=int(time.time() * 1000)))

		return frame.data

	def send_read_pdu (self, data: bytes) -> bytes:
		if platform.startswith('win32'):
			self.send_pdu(data)
			return self.read_pdu()
		self.buffer_push(RawPacket(direction=PacketDirection.OUTGOING, data=data, timestamp=int(time.time()*1000)))
		response = self.isotp.sr1(ISOTP(bytes(data)), verbose=False, timeout=self.hardware.get_timeout())

		if not response:
			raise TimeoutException

		self.buffer_push(RawPacket(direction=PacketDirection.INCOMING, data=response.data, timestamp=int(time.time() * 1000)))

		return response.data