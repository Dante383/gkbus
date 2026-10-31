import errno
import logging
from typing import TYPE_CHECKING, Any

from ...channel import CanFilter, IsoTpLink, IsoTpParams
from ...exceptions import ChannelException, OpeningChannelException
from ..python_can.python_can_channel import PythonCanChannel
from .kernel_isotp_link import KernelIsoTpLink

if TYPE_CHECKING:
	from pyroute2 import IPRoute
	from pyroute2.netlink.rtnl.ifinfmsg import ifinfmsg

logger = logging.getLogger(__name__)

#: IFF_UP
LINK_UP = 1
#: netlink errors meaning we lack CAP_NET_ADMIN
PERMISSION_ERRORS = (errno.EPERM, errno.EACCES)

class SocketCanChannel(PythonCanChannel):
	'''
	CAN bus on a Linux SocketCAN network interface (e.g. can0).

	An interface that's already up at the right bitrate is used as it is and left up. Otherwise
	opening sets the bitrate and brings it up, and closing takes it down again - that needs
	CAP_NET_ADMIN (root).
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
		self._link_configured = False

	def isotp (self, tx_id: int, rx_id: int, params: IsoTpParams | None = None) -> IsoTpLink:
		return KernelIsoTpLink(self.ifname, tx_id, rx_id, params)

	def _open (self) -> None:
		# pyroute2 is only installed on Linux
		from pyroute2 import IPRoute, NetlinkError

		try:
			with IPRoute() as ipr:
				index = self._link_index(ipr)
				link = ipr.get_links(index)[0]
				if self._link_ready(link):
					return
				try:
					self._configure_link(ipr, index, link)
				except NetlinkError as e:
					if e.code in PERMISSION_ERRORS:
						raise OpeningChannelException(self._no_permission(link)) from e
					raise
		except OpeningChannelException:
			raise
		except (NetlinkError, OSError, RuntimeError) as e:
			raise OpeningChannelException(
				'Configuring {} failed: {}'.format(self.ifname, e)
			) from e

	def _link_ready (self, link: 'ifinfmsg') -> bool:
		'''
		Up, and at our bitrate if it has one (virtual interfaces don't)
		'''
		if not link['flags'] & LINK_UP:
			return False
		bitrate = self._link_bitrate(link)
		if bitrate is not None and bitrate != self.bitrate:
			logger.info('{} runs at {} bit/s, reconfiguring it to {}'.format(
				self.ifname, bitrate, self.bitrate
			))
			return False
		return True

	def _configure_link (self, ipr: 'IPRoute', index: int, link: 'ifinfmsg') -> None:
		if link['flags'] & LINK_UP:
			ipr.link('set', index=index, state='down')
		if self._has_bitrate(link):
			ipr.link('set', index=index, kind='can', can_bittiming={'bitrate': self.bitrate})
		ipr.link('set', index=index, state='up')
		self._link_configured = True

	def _no_permission (self, link: 'ifinfmsg') -> str:
		if self._has_bitrate(link):
			setup = 'sudo ip link set {} down; sudo ip link set {} up type can bitrate {}'.format(
				self.ifname, self.ifname, self.bitrate
			)
		else:
			setup = 'sudo ip link set {} up'.format(self.ifname)
		if not link['flags'] & LINK_UP:
			problem = '{} is down'.format(self.ifname)
		else:
			problem = '{} runs at {} bit/s, {} needed'.format(
				self.ifname, self._link_bitrate(link), self.bitrate
			)
		return '{} and gkbus has no permission to configure it. Run: {}'.format(problem, setup)

	def _close (self) -> None:
		from pyroute2 import IPRoute, NetlinkError

		# an interface that was already up isn't ours to take down
		if not self._link_configured:
			return
		self._link_configured = False
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

	@staticmethod
	def _has_bitrate (link: 'ifinfmsg') -> bool:
		'''
		Physical CAN interface, not vcan or similar
		'''
		return link.get(('linkinfo', 'kind')) == 'can'

	@staticmethod
	def _link_bitrate (link: 'ifinfmsg') -> int | None:
		bittiming = link.get(('linkinfo', 'data', 'can_bittiming')) or {}
		return bittiming.get('bitrate')

	def _link_index (self, ipr: 'IPRoute') -> int:
		indexes = ipr.link_lookup(ifname=self.ifname)
		if not indexes:
			raise RuntimeError('CAN interface not found: {}'.format(self.ifname))
		return indexes[0]
