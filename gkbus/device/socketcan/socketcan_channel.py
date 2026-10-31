from typing import TYPE_CHECKING, Any

from ...channel import CanFilter, IsoTpLink, IsoTpParams
from ...exceptions import ChannelException, OpeningChannelException
from ..python_can.python_can_channel import PythonCanChannel
from .kernel_isotp_link import KernelIsoTpLink

if TYPE_CHECKING:
	from pyroute2 import IPRoute

#: IFF_UP
LINK_UP = 1

class SocketCanChannel(PythonCanChannel):
	'''
	CAN bus on a Linux SocketCAN network interface (e.g. can0).

	Opening always takes the interface down, sets the bitrate and brings it back up, so nothing
	is left over from before. Closing takes it down again. Both need CAP_NET_ADMIN.
	ISO-TP is done by the kernel. The raw socket for send() and recv() is only created once
	they're used, so it doesn't queue up frames nobody reads
	'''

	def __init__ (
		self,
		ifname: str,
		bitrate: int = 500_000,
		filters: list[CanFilter] | None = None,
	) -> None:
		'''
		:param ifname: network interface name, for example can0
		'''
		super().__init__('socketcan', ifname, bitrate=bitrate, filters=filters)
		self.ifname = ifname

	def isotp (self, tx_id: int, rx_id: int, params: IsoTpParams | None = None) -> IsoTpLink:
		return KernelIsoTpLink(self.ifname, tx_id, rx_id, params)

	def _open (self) -> None:
		# pyroute2 is only installed on Linux
		from pyroute2 import IPRoute, NetlinkError

		try:
			with IPRoute() as ipr:
				index = self._link_index(ipr)
				link = ipr.get_links(index)[0]
				if link['flags'] & LINK_UP:
					ipr.link('set', index=index, state='down')
				# virtual interfaces have no bitrate
				if link.get(('linkinfo', 'kind')) != 'vcan':
					ipr.link(
						'set', index=index, kind='can', can_bittiming={'bitrate': self.bitrate}
					)
				ipr.link('set', index=index, state='up')
		except (NetlinkError, OSError, RuntimeError) as e:
			raise OpeningChannelException(
				'Configuring {} failed: {}'.format(self.ifname, e)
			) from e

	def _close (self) -> None:
		from pyroute2 import IPRoute, NetlinkError

		try:
			with IPRoute() as ipr:
				ipr.link('set', index=self._link_index(ipr), state='down')
		except (NetlinkError, OSError, RuntimeError) as e:
			raise ChannelException('Taking {} down failed: {}'.format(self.ifname, e)) from e

	def _bus_filters (self) -> dict[str, Any]:
		'''
		Filters are applied by the kernel
		'''
		return {'can_filters': self._python_can_filters()}

	def _apply_filters (self) -> None:
		if self._bus is not None:
			self._bus.set_filters(self._python_can_filters())

	def _python_can_filters (self) -> list[dict[str, int]] | None:
		return [
			{'can_id': x.can_id, 'can_mask': x.can_mask} for x in self.get_filters()
		] or None

	def _link_index (self, ipr: 'IPRoute') -> int:
		indexes = ipr.link_lookup(ifname=self.ifname)
		if not indexes:
			raise RuntimeError('CAN interface not found: {}'.format(self.ifname))
		return indexes[0]
