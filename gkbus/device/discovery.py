import logging
from collections.abc import Iterable

from ..exceptions import DeviceException
from .device_abc import Bus, DeviceABC
from .python_can import PythonCanDevice
from .serial import SerialKLineDevice
from .socketcan import SocketCanDevice

logger = logging.getLogger(__name__)

#: every known device type, in the order find_device() asks them - most specific first,
#: serial ports last since anything could be one
DEVICE_TYPES: list[type[DeviceABC]] = [PythonCanDevice, SocketCanDevice, SerialKLineDevice]

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

def find_device (port: str, buses: Iterable[Bus] | None = None) -> DeviceABC:
	'''
	Create a device from a port string, e.g. /dev/ttyUSB0, COM3, can0 or pcan:PCAN_USBBUS1.
	Nothing is scanned or opened

	:param buses: only consider device types supporting any of these buses
	:raises DeviceException: no device type recognises the port
	'''
	wanted = frozenset(Bus) if buses is None else frozenset(buses)
	for device_type in DEVICE_TYPES:
		if not device_type.buses & wanted:
			continue
		device = device_type.from_port(port)
		if device is not None:
			return device
	raise DeviceException('No device found for port {}'.format(port))
