import logging
import os
from typing import Self

import serial.tools.list_ports
from serial.tools.list_ports_common import ListPortInfo

from ...channel import KLineTiming
from ..device_abc import Bus, DeviceABC
from ..j2534.registry import ADAPTER_USB_IDS
from ..obd_pin import ObdPin
from ..python_can.backends import SLCAN_USB_IDS
from .serial_kline_channel import SerialKLineChannel

logger = logging.getLogger(__name__)

TTY_DIR = '/sys/class/tty'


class SerialKLineDevice(DeviceABC):
	'''
	K-Line adapter on a serial port (KKL cables and the like), through pyserial.
	There's nothing to open on the device itself - the serial port is opened by the K-Line channel.
	Its wiring is fixed and it can't ground pins, so the user is asked to wire those
	'''

	buses = frozenset({Bus.KLINE})

	def __init__ (
		self,
		port: str,
		manufacturer: str | None = None,
		serial_number: str | None = None,
	) -> None:
		'''
		:param port: serial port, for example /dev/ttyUSB0 or COM3. pyserial URLs work too
		'''
		super().__init__()
		self.port = port
		self.manufacturer = manufacturer
		self.serial_number = serial_number

	def kline (
		self,
		baudrate: int = 10400,
		pin: ObdPin = ObdPin.K_LINE,
		timing: KLineTiming | None = None,
	) -> SerialKLineChannel:
		'''
		Get the K-Line channel. Opens the device (not the channel) if it wasn't open.
		The channel isn't opened - open it yourself, or let the transport do it

		:param pin: the adapter can't switch pins - for any other than 7 a warning that its
			K-Line has to be wired to this pin is logged
		:param timing: kept on the channel, the serial channel doesn't use it yet
		:raises ChannelInUseException: the K-Line channel handed out earlier is still open
		:raises ValueError: the pin is ground or battery
		:raises DeviceException: the pin is grounded
		'''
		pin = self._obd_pin(pin)
		channel = self._hand_out(
			Bus.KLINE,
			lambda: SerialKLineChannel(self.port, baudrate=baudrate, pin=pin, timing=timing),
			pins=frozenset({pin}),
		)
		if pin != ObdPin.K_LINE:
			logger.warning('{} can\'t switch pins, make sure its K-Line is wired to {}'.format(
				self.description(), pin
			))
		return channel

	def description (self) -> str:
		details = ' '.join([x for x in [self.manufacturer, self.serial_number] if x])
		return '{} - {}'.format(self.port, details) if details else self.port

	@classmethod
	def discover (cls) -> list[Self]:
		'''
		Ports most likely to be a K-Line adapter come first: USB-serial converters (ttyUSB,
		USB COM ports on Windows), then the rest (e.g. ttyS).
		Skipped: CAN adapters that show up as a serial port (slcan), J2534 adapters (the Tactrix
		OpenPort is a USB CDC ACM device, J2534Device drives it), other USB CDC ACM devices
		(ttyACM - Arduinos, modems) and ports without a UART behind them. Pass one of these ports
		explicitly to use it anyway
		'''
		return [
			cls(port.device, manufacturer=port.manufacturer, serial_number=port.serial_number)
			for port in sorted(sorted(serial.tools.list_ports.comports()), key=cls._port_priority)
			if (port.vid, port.pid) not in SLCAN_USB_IDS
			and (port.vid, port.pid) not in ADAPTER_USB_IDS
			and not port.name.startswith('ttyACM')
			and not cls._is_phantom(port)
		]

	@classmethod
	def from_port (cls, port: str) -> Self | None:
		'''
		Anything can be a serial port, so this always succeeds - it's asked last
		'''
		return cls(port)

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

	@staticmethod
	def _is_phantom (port: ListPortInfo) -> bool:
		'''
		Linux registers ttyS ports even when there's no UART behind them (sysfs type 0,
		PORT_UNKNOWN). pyserial stopped filtering them out with kernel 6.5
		'''
		try:
			with open(os.path.join(TTY_DIR, port.name, 'type')) as file:
				return file.read().strip() == '0'
		except OSError:
			return False
