'''
Quirks of the python-can interfaces gkbus knows: how to open them, clean up after them
and find connected adapters. Any other python-can interface works with the defaults
'''
from dataclasses import dataclass
from sys import platform
from typing import Any

import can

#: USB (VID, PID) of serial devices speaking slcan
SLCAN_USB_IDS: dict[tuple[int, int], str] = {(0xAD50, 0x60C4): 'CANable'}
#: shortest gs_usb read. It rounds the timeout to whole milliseconds and 0 means wait forever
GS_USB_MIN_WAIT = 0.001


@dataclass(frozen=True)
class DiscoveredChannel:
	channel: str
	manufacturer: str | None = None
	serial_number: str | None = None

class PythonCanBackend:
	'''
	One python-can interface. The base class passes the channel through as is
	'''

	def __init__ (self, interface: str) -> None:
		self.interface = interface

	def bus_kwargs (self, channel: str) -> dict[str, Any]:
		'''
		Arguments for can.Bus() besides interface and bitrate
		'''
		return {'channel': channel}

	def before_open (self) -> None:
		pass

	def after_close (self, bus: can.BusABC) -> None:
		pass

	def recv (self, bus: can.BusABC, timeout: float) -> can.Message | None:
		'''
		One read of up to timeout seconds, None if nothing came in
		'''
		return bus.recv(timeout)

	def discover (self) -> list[DiscoveredChannel]:
		return []

class PcanBackend(PythonCanBackend):
	'''
	PEAK PCAN adapters
	'''
	def discover (self) -> list[DiscoveredChannel]:
		channels = []
		for config in can.detect_available_configs(interfaces=[self.interface]):
			if config.get('channel') is None:
				continue
			serial_number = config.get('serial_number')
			if serial_number is None:
				serial_number = config.get('serial')
			channels.append(DiscoveredChannel(
				channel=str(config['channel']),
				manufacturer='Peak',
				serial_number=str(serial_number) if serial_number is not None else None,
			))
		return channels

class VectorBackend(PythonCanBackend):
	'''
	Vector adapters, the channel is an index
	'''
	def bus_kwargs (self, channel: str) -> dict[str, Any]:
		return {'channel': int(channel), 'app_name': None}

	def discover (self) -> list[DiscoveredChannel]:
		channels = []
		for config in can.detect_available_configs(interfaces=[self.interface]):
			if config.get('channel') is None:
				continue
			if getattr(config.get('hw_type'), 'name', '') == 'XL_HWTYPE_VIRTUAL':
				continue
			serial_number = config.get('serial_number')
			if serial_number is None:
				serial_number = config.get('serial')
			channels.append(DiscoveredChannel(
				channel=str(config['channel_index']),
				manufacturer='Vector',
				serial_number=str(serial_number) if serial_number is not None else None,
			))
		return channels

class SlcanBackend(PythonCanBackend):
	'''
	Serial-line CAN adapters (CANable with slcan firmware), the channel is the serial port
	'''
	def discover (self) -> list[DiscoveredChannel]:
		from serial.tools import list_ports

		return [
			DiscoveredChannel(
				channel=port.device,
				manufacturer=SLCAN_USB_IDS[(port.vid, port.pid)],
				serial_number=port.serial_number,
			)
			for port in list_ports.comports()
			if (port.vid, port.pid) in SLCAN_USB_IDS
		]

class GsUsbBackend(PythonCanBackend):
	'''
	GS-USB adapters (CANable with candleLight firmware) through libusb, the channel is an index
	'''
	def bus_kwargs (self, channel: str) -> dict[str, Any]:
		return {'channel': int(channel)}

	def before_open (self) -> None:
		_initialize_libusb()

	def after_close (self, bus: can.BusABC) -> None:
		from usb.util import dispose_resources

		# A stopped bus can still retain the USB handle
		dispose_resources(bus.gs_usb.gs_usb)

	def recv (self, bus: can.BusABC, timeout: float) -> can.Message | None:
		# Single driver read, bypassing bus.recv(): it retries whatever is left of the
		# timeout, and a leftover under 0.5 ms rounds to 0 - which blocks forever
		message, _ = bus._recv_internal(max(timeout, GS_USB_MIN_WAIT))
		# the adapter echoes every frame we send
		if message is not None and not message.is_rx:
			return None
		return message

	def discover (self) -> list[DiscoveredChannel]:
		from can.interfaces.gs_usb import GsUsb
		from usb.util import dispose_resources

		_initialize_libusb()
		channels = []
		for index, adapter in enumerate(GsUsb.scan()):
			try:
				manufacturer = adapter.gs_usb.manufacturer or 'Unknown'
				serial_number = adapter.gs_usb.serial_number or None
			finally:
				# This prevents "usb.core.USBError: [Errno 13] Access denied
				# (insufficient permissions)"
				dispose_resources(adapter.gs_usb)
			channels.append(DiscoveredChannel(
				channel=str(index),
				manufacturer=manufacturer,
				serial_number=serial_number,
			))
		return channels

BACKENDS: dict[str, PythonCanBackend] = {
	backend.interface: backend for backend in [
		PcanBackend('pcan'),
		VectorBackend('vector'),
		SlcanBackend('slcan'),
		GsUsbBackend('gs_usb'),
	]
}

def backend_for (interface: str) -> PythonCanBackend:
	return BACKENDS.get(interface) or PythonCanBackend(interface)

def _initialize_libusb () -> None:
	'''
	Load system libusb or the packaged Windows DLL before gs_usb scans
	'''
	from usb.backend import libusb1

	if libusb1.get_backend() is not None:
		return
	if platform.startswith('win32'):
		from libusb_package import find_library

		if libusb1.get_backend(find_library=find_library) is not None:
			return
	raise RuntimeError('Unable to load the libusb backend required by GS-USB')
