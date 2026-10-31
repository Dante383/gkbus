import logging
from collections.abc import Iterable

from .device_abc import Bus, DeviceABC
from .python_can_device import PythonCanDevice
from .serial_kline_device import SerialKLineDevice
from .socketcan_device import SocketCanDevice

logger = logging.getLogger(__name__)

DEVICE_TYPES: list[type[DeviceABC]] = [SerialKLineDevice, SocketCanDevice, PythonCanDevice]

def discover (buses: Iterable[Bus] | None = None) -> list[DeviceABC]:
	'''
	Find connected devices of every known type that support any of the requested buses.
	Nothing is opened

	:param buses: buses you're interested in, e.g. {Bus.KLINE, Bus.CANBUS}.
		All buses if not provided
	:return: unopened device instances
	'''
	wanted = frozenset(Bus) if buses is None else frozenset(buses)
	devices: list[DeviceABC] = []

	for device_type in DEVICE_TYPES:
		if not device_type.buses & wanted:
			continue
		try:
			devices.extend(device_type.discover())
		except Exception as e:
			logger.warning('Discovering {} devices failed: {}'.format(device_type.__name__, e))

	return devices
