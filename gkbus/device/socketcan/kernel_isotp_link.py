import errno

import isotp

from ...channel import IsoTpLink, IsoTpParams
from ...exceptions import ChannelException, OpeningChannelException, TimeoutException


class KernelIsoTpLink(IsoTpLink):
	'''
	ISO-TP done by the Linux kernel (can-isotp module) on a SocketCAN interface.
	Frames for the link are handled in the kernel, the channel's raw socket isn't involved
	'''

	def __init__ (
		self,
		ifname: str,
		tx_id: int,
		rx_id: int,
		params: IsoTpParams | None = None,
	) -> None:
		super().__init__(tx_id, rx_id, params)
		self.ifname = ifname
		self._socket: isotp.socket | None = None

	def open (self) -> None:
		if self._socket is not None:
			return
		sock = None
		try:
			sock = isotp.socket()
			# send() returns once the whole payload is out, so failures (no flow control
			# from the ECU) show up there instead of on the next recv()
			flags = isotp.socket.flags.WAIT_TX_DONE
			padding = self.params.padding
			if padding is not None:
				flags |= isotp.socket.flags.TX_PADDING | isotp.socket.flags.RX_PADDING
			sock.set_opts(optflag=flags, txpad=padding, rxpad=padding)
			sock.set_fc_opts(bs=self.params.blocksize, stmin=self.params.stmin)
			sock.bind(self.ifname, self.address())
		except (OSError, NotImplementedError) as e:
			# NotImplementedError: Python built without CAN_ISOTP, OSError: no can-isotp module
			if sock is not None:
				sock.close()
			raise OpeningChannelException(e) from e
		self._socket = sock

	def is_open (self) -> bool:
		return self._socket is not None

	def close (self) -> None:
		if self._socket is None:
			return
		sock, self._socket = self._socket, None
		sock.close()

	def send (self, data: bytes, timeout: float) -> None:
		sock = self._open_socket()
		try:
			sock.settimeout(timeout)
			sock.send(data)
		except OSError as e:
			raise self._translate(e) from e

	def recv (self, timeout: float) -> bytes:
		sock = self._open_socket()
		try:
			sock.settimeout(timeout)
			return sock.recv()
		except OSError as e:
			raise self._translate(e) from e

	def _open_socket (self) -> isotp.socket:
		if self._socket is None:
			raise ChannelException('ISO-TP link is not open')
		return self._socket

	@staticmethod
	def _translate (error: OSError) -> ChannelException:
		'''
		Socket timeouts and the kernel's own ISO-TP timeouts (ECOMM - e.g. missing flow
		control or consecutive frames) are timeouts, anything else is a channel failure
		'''
		if isinstance(error, TimeoutError) or error.errno == errno.ECOMM:
			return TimeoutException(error)
		return ChannelException(error)
