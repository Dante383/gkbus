from ..channel import CanChannel, IsoTpLink, IsoTpParams
from ..exceptions import ChannelException
from .transport_abc import PacketDirection, TransportABC


class Kwp2000OverCanTransport (TransportABC):
	'''
	KWP2000 over CAN: PDUs go over an ISO-TP link (ISO 15765-2) between tx_id and rx_id.
	The link is done by the kernel on SocketCAN and in software everywhere else
	'''

	channel: CanChannel

	def __init__ (
		self,
		channel: CanChannel,
		tx_id: int,
		rx_id: int,
		timeout: float = 1,
		isotp_params: IsoTpParams | None = None,
	) -> None:
		'''
		:param channel: CAN bus channel, e.g. from device.canbus()
		:param tx_id: CAN identifier requests are sent on
		:param rx_id: CAN identifier responses come from
		:param timeout: seconds to wait for a response
		:param isotp_params: padding, stmin and block size. Padded with 0xCC by default
		'''
		super().__init__(channel, tx_id, rx_id, timeout)
		self.isotp_params = isotp_params
		self._link: IsoTpLink | None = None

	def send_pdu (self, pdu: bytes) -> int:
		self._get_link().send(pdu, self.timeout)
		self._record(PacketDirection.OUTGOING, pdu)

		return len(pdu)

	def read_pdu (self, timeout: float | None = None) -> bytes:
		data = self._get_link().recv(self._timeout(timeout))
		self._record(PacketDirection.INCOMING, data)

		return data

	def _open_link (self) -> None:
		link = self.channel.isotp(self.tx_id, self.rx_id, self.isotp_params)
		link.open()
		self._link = link

	def _close_link (self) -> None:
		if self._link is not None:
			link, self._link = self._link, None
			link.close()

	def _get_link (self) -> IsoTpLink:
		if self._link is None:
			raise ChannelException('Transport is not open')
		return self._link
