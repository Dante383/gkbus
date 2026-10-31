from abc import abstractmethod

from .can_frame import CanFilter, CanFrame
from .channel_abc import ChannelABC
from .isotp_link import IsoTpLink, IsoTpParams, SoftwareIsoTpLink


class CanChannel(ChannelABC):
	'''
	CAN bus - send and receive single frames.
	Only one consumer should read a CAN channel at a time
	'''

	def __init__ (self, bitrate: int = 500_000, filters: list[CanFilter] | None = None) -> None:
		self.bitrate = bitrate
		self._filters: list[CanFilter] = list(filters or [])

	@abstractmethod
	def send (self, frame: CanFrame) -> None:
		pass

	@abstractmethod
	def recv (self, timeout: float) -> CanFrame:
		'''
		Receive the next frame passing the filters

		:param timeout: seconds to wait for it
		:raises TimeoutException: no frame passed the filters in time
		'''

	def get_bitrate (self) -> int:
		return self.bitrate

	def get_filters (self) -> list[CanFilter]:
		return list(self._filters)

	def set_filters (self, filters: list[CanFilter] | None) -> None:
		'''
		Receive only frames matching any of the filters, takes effect immediately

		:param filters: None or an empty list to receive everything
		'''
		self._filters = list(filters or [])
		self._apply_filters()

	def isotp (self, tx_id: int, rx_id: int, params: IsoTpParams | None = None) -> IsoTpLink:
		'''
		Create an ISO-TP link on this channel. The link isn't opened.
		Done in software here - channels that can do ISO-TP natively return their own link
		'''
		return SoftwareIsoTpLink(self, tx_id, rx_id, params)

	def _apply_filters (self) -> None:
		'''
		Hook for pushing the filters down to the hardware or driver. recv() has to
		apply them anyway, this only saves work
		'''

	def _matches_filters (self, frame: CanFrame) -> bool:
		return not self._filters or any(f.matches(frame.identifier) for f in self._filters)
