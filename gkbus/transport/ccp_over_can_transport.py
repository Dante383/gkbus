import time

from ..channel import CanChannel, CanFilter, CanFrame
from ..exceptions import TimeoutException
from .transport_abc import PacketDirection, TransportABC

#: first byte of a Command Return Message
CRM_PID = 0xFF

class CcpOverCanTransport (TransportABC):
	'''
	CAN Calibration Protocol transport.
	Nothing interesting here - CCP doesn't use ISOTP or any other way to break
	chunks of data into messages - each command or response must fit within 8 bytes of
	a standard CAN frame.
	While open, the channel only receives rx_id - the filters it had are restored on close
	'''

	channel: CanChannel

	def __init__ (
		self,
		channel: CanChannel,
		tx_id: int,
		rx_id: int,
		crm_only: bool = False,
		timeout: float = 1,
	) -> None:
		'''
		:param channel: CAN bus channel, e.g. from device.canbus()
		:param tx_id: CAN identifier of Command Receive Objects (requests)
		:param rx_id: CAN identifier of Data Transmission Objects (responses)
		:param crm_only: skip everything but Command Return Messages, e.g. DAQ data while flashing
		:param timeout: seconds to wait for a response
		'''
		super().__init__(channel, tx_id, rx_id, timeout)
		self.crm_only = crm_only
		self._previous_filters: list[CanFilter] = []

	def send_pdu (self, pdu: bytes) -> int:
		self.channel.send(CanFrame(self.tx_id, pdu))

		self._record(PacketDirection.OUTGOING, pdu)

		return len(pdu)

	def read_pdu (self, timeout: float | None = None) -> bytes:
		deadline = time.monotonic() + self._timeout(timeout)

		while True:
			remaining = deadline - time.monotonic()
			if remaining <= 0:
				raise TimeoutException

			frame = self.channel.recv(remaining)
			data = frame.data

			# Flashing mode:
			# accept CRM packets only
			if self.crm_only and (
				frame.identifier != self.rx_id or len(data) < 3 or data[0] != CRM_PID
			):
				continue

			self._record(PacketDirection.INCOMING, data)

			return data

	def _open_link (self) -> None:
		self._previous_filters = self.channel.get_filters()
		self.channel.set_filters([CanFilter.for_id(self.rx_id)])

	def _close_link (self) -> None:
		if self.channel.is_open():
			self.channel.set_filters(self._previous_filters)
