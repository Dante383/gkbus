from typing import Self

import serial.tools.list_ports
from serial.tools.list_ports_common import ListPortInfo

from ..hardware import KLineHardware
from ..hardware.can_hardware import SLCAN_USB_IDS
from .device_abc import Bus, DeviceABC


class SerialKLineDevice(DeviceABC):
	'''
	K-Line adapter on a serial port (KKL cables and the like), through pyserial.
	There's nothing to open on the device itself - the serial port is opened by the K-Line hardware
	'''

	buses = frozenset({Bus.KLINE})

	def __init__ (
		self,
		port: str,
		manufacturer: str | None = None,
		serial_number: str | None = None,
	) -> None:
		'''
		:param port: serial port, for example /dev/ttyUSB0 or COM3
		'''
		super().__init__()
		self.port = port
		self.manufacturer = manufacturer
		self.serial_number = serial_number

	def kline (self, baudrate: int = 10400, timeout: float = 2) -> KLineHardware:
		'''
		Get K-Line hardware on this device. Opens the device (not the hardware) if it wasn't open.
		The hardware isn't opened - open it yourself, or let the transport do it

		:raises ChannelInUseException: K-Line hardware handed out earlier is still open
		'''
		return self._hand_out(
			Bus.KLINE,
			lambda: KLineHardware(self.port, baudrate=baudrate, timeout=timeout),
		)

	def description (self) -> str:
		details = ' '.join([x for x in [self.manufacturer, self.serial_number] if x])
		return '{} - {}'.format(self.port, details) if details else self.port

	@classmethod
	def discover (cls) -> list[Self]:
		'''
		Ports most likely to be a K-Line adapter come first: USB-serial converters (ttyUSB),
		then other USB devices (e.g. ttyACM), then the rest (e.g. ttyS).
		CAN adapters that show up as a serial port (slcan) are skipped
		'''
		return [
			cls(port.device, manufacturer=port.manufacturer, serial_number=port.serial_number)
			for port in sorted(sorted(serial.tools.list_ports.comports()), key=cls._port_priority)
			if (port.vid, port.pid) not in SLCAN_USB_IDS
		]

	@staticmethod
	def _port_priority (port: ListPortInfo) -> int:
		"""
		On Linux puts ttyUSB ports first in order, on Windows prioritizes USB COM ports
		"""
		if port.name.startswith('ttyUSB'):
			return 0
		if port.vid is not None:
			return 1
		return 2
