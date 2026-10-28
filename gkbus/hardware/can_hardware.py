import os
import time
from dataclasses import dataclass
from threading import Lock
from sys import platform
from enum import Enum

from scapy.config import conf
from typing_extensions import Self

if platform.startswith('win32'):
	conf.contribs['CANSocket'] = {'use-python-can': True}

else:
	# If you're a linux guest in a windows host, this will cause
	# "no data received, try increasing stmin" issues, ranging 
	# from occasional to very common.
	# Best guess so far is that since python-can won't use the
	# native ISO-TP kernel module, the issue must be closely related
	# to some low level device access handling in the passthrough hypervisor
	#
	# Case in point used a Canable interface with Candlelight firmware,
	# Ubuntu 22.04 (5.15.0 kernel) guest on a Windows 10 v1803 host, 
	# through VMware Workstation 16
	conf.contribs['CANSocket'] = {'use-python-can': False}

from scapy.contrib.cansocket import CANSocket
from scapy.error import Scapy_Exception
from scapy.layers.can import CAN, CAN_MAX_DLEN, CAN_MTU

from .hardware_abc import (
	HardwareABC,
	HardwarePort,
	OpeningPortException,
	RawFrame,
	TimeoutException,
)

CAN_HEADER_LEN = CAN_MTU-CAN_MAX_DLEN

@dataclass
class CanFilter:
	"""CAN identifier and mask used to filter received frames."""
	can_id: int
	can_mask: int = 0x7ff

class CanBackend(Enum):
	"""Supported CAN hardware backends."""
	PCAN = "pcan"
	VECTOR = "vector"
	SLCAN = "slcan"
	GS_USB = "gs_usb"

class CanHardware(HardwareABC):
	"""Shared CAN behaviour and backwards-compatible backend factory.

	``CanHardware(port, ...)`` chooses a concrete backend from the port string.
	Concrete classes can also be instantiated directly.
	"""

	def __new__(cls, port: str, *args, **kwargs):
		if platform.startswith("win32"):
			prefix = port.split(":", 1)[0] if ":" in port else ""
			backends = {
				CanBackend.PCAN: PcanCanHardware,
				CanBackend.VECTOR: VectorCanHardware,
				CanBackend.SLCAN: SlcanCanHardware,
				CanBackend.GS_USB: GsUsbCanHardware,
			}
			try:
				backend_type = CanBackend(prefix)
				backend = backends[backend_type]
			except ValueError as exc:
				raise ValueError(
					f"Unsupported CAN interface: {prefix or port}"
				) from exc
			return object.__new__(backend)
		if platform.startswith("linux"):
			return object.__new__(SocketCanHardware)
		raise RuntimeError(f"Unsupported platform: {platform}")
		return object.__new__(cls)

	def __init__(
		self,
		port: str,
		bitrate: int = 500_000,
		timeout: float = 1,
		filters: list[CanFilter] | None = None,
	) -> None:
		self.port = port
		self.bitrate = bitrate
		self.timeout = timeout
		self.filters = list(filters or [])
		self.socket = None
		self._raw = False
		self._isotp_stack = None
		self._close_lock = Lock()

	def _build_filters(self) -> list[dict] | None:
		"""Convert filters to the dictionary format expected by Scapy."""
		filters = [
			{"can_id": can_filter.can_id, "can_mask": can_filter.can_mask}
			for can_filter in self.filters
		]
		return filters or None

	def _create_socket(self, **kwargs):
		"""Use a direct python-can bus for Windows ISO-TP, or Scapy for raw CAN."""
		if self._raw:
			from can import Bus

			return Bus(**kwargs)
		return CANSocket(**kwargs)

	def _open_socket(self):
		"""Create the backend socket. Implemented by concrete subclasses."""
		raise NotImplementedError

	def open(self, *, raw: bool = False) -> bool:
		"""Configure and open the selected CAN interface."""
		self._raw = raw
		try:
			self.socket = self._open_socket()
		except (OSError, Scapy_Exception, ValueError, RuntimeError) as exc:
			raise OpeningPortException(exc) from exc
		return True

	def is_open(self) -> bool:
		if self._raw:
			return self.socket is not None and not self.socket._is_shutdown
		return self.socket is not None and not getattr(self.socket, "closed", True)

	def read(self, length: int) -> RawFrame:
		"""Read one CAN frame, raising ``TimeoutException`` on timeout."""
		if self.socket is None:
			raise RuntimeError("CAN interface is not open")
		try:
			packet = self.socket.sniff(timeout=self.timeout, count=1)[0]
		except IndexError as exc:
			raise TimeoutException from exc
		return RawFrame(identifier=packet.identifier, data=packet.data)

	def write(self, frame: RawFrame) -> int:
		"""Transmit a frame and return the number of CAN payload bytes."""
		if self.socket is None:
			raise RuntimeError("CAN interface is not open")
		packet = CAN(identifier=frame.identifier, data=frame.data)
		return self.socket.send(packet) - CAN_HEADER_LEN

	def get_filters(self) -> list[CanFilter]:
		return list(self.filters)

	def set_filters(self, filters: list[CanFilter]) -> Self:
		"""Replace filters, restarting the socket if it is currently open."""
		self.filters = list(filters)
		if self.is_open():
			self.close()
			self.open()
		return self

	def add_filter(self, can_filter: CanFilter) -> Self:
		return self.set_filters(self.get_filters() + [can_filter])

	def close(self) -> None:
		# GUI workers and exception handlers may close the same bus concurrently.
		with self._close_lock:
			if self._isotp_stack is not None:
				# Stop the receive worker while its CAN bus is still open.
				self._isotp_stack.stop()
				self._isotp_stack = None
			if self.socket is not None:
				if self._raw:
					try:
						self.socket.shutdown()
					finally:
						if isinstance(self, GsUsbCanHardware):
							from usb.util import dispose_resources

							# A stopped ISO-TP stack can still retain the bus and USB handle.
							dispose_resources(self.socket.gs_usb.gs_usb)
				else:
					self.socket.close()
				self.socket = None

	def set_baudrate(self, baudrate: int) -> Self:
		if baudrate == self.bitrate:
			return self
		raise NotImplementedError(
			"Changing bitrate requires closing and reopening the interface"
		)

	def get_baudrate(self) -> int:
		return self.bitrate

	def set_timeout(self, timeout: float) -> Self:
		self.timeout = timeout
		if self.socket is not None:
			self.socket.timeout = timeout
		return self

	@staticmethod
	def available_ports() -> list[HardwarePort]:
		"""Discover supported CAN interfaces using the existing public API."""
		if platform.startswith("linux"):
			net_dir = "/sys/class/net"
			ports: list[HardwarePort] = []
			if not os.path.isdir(net_dir):
				return ports
			for interface in os.listdir(net_dir):
				type_path = os.path.join(net_dir, interface, "type")
				try:
					with open(type_path, "r", encoding="ascii") as handle:
						if handle.read().strip() == "280":
							ports.append(HardwarePort(port=interface, port_name=interface))
				except OSError:
					continue
			return ports
		if platform.startswith("win32"):
			return _available_ports_windows()
		return []

class SocketCanHardware(CanHardware):
	"""Linux SocketCAN backend configured through pyroute2."""

	def _open_socket(self):
		from pyroute2 import IPRoute

		with IPRoute() as ipr:
			indexes = ipr.link_lookup(ifname=self.port)
			if not indexes:
				raise RuntimeError(f"CAN interface not found: {self.port}")
			index = indexes[0]
			link = ipr.get_links(index)[0]

			# Bitrate can only be changed while the interface is down.
			if link["flags"] & 1:
				ipr.link("set", index=index, state="down")
			ipr.link(
				"set",
				index=index,
				kind="can",
				can_bittiming={"bitrate": self.bitrate},
			)
			ipr.link("set", index=index, state="up")

		return CANSocket(channel=self.port, can_filters=self._build_filters())

	def close(self) -> None:
		from pyroute2 import IPRoute

		try:
			super().close()
		finally:
			with IPRoute() as ipr:
				indexes = ipr.link_lookup(ifname=self.port)
				if indexes:
					ipr.link("set", index=indexes[0], state="down")

class PcanCanHardware(CanHardware):
	"""PEAK PCAN adapter backend (Windows/python-can)."""

	# TEMPORARY Workaround: force software filtering for PCAN
	if platform.startswith("win32"):
		from scapy.contrib import cansocket_python_can

		cansocket_python_can._HW_FILTERED_INTERFACES = frozenset(
			interface
			for interface in cansocket_python_can._HW_FILTERED_INTERFACES
			if interface != "pcan"
		)

	def _open_socket(self):
		_, channel = self.port.split(":", 1)
		return self._create_socket(
			bustype=CanBackend.PCAN.value, 
			channel=channel, 
			bitrate=self.bitrate, 
			can_filters=self._build_filters()
		)


class VectorCanHardware(CanHardware):
	"""Vector adapter backend (Windows/python-can)."""

	def _open_socket(self):
		_, channel = self.port.split(":", 1)
		return self._create_socket(
			bustype=CanBackend.VECTOR.value,
			channel=int(channel),
			app_name=None,
			bitrate=self.bitrate,
			can_filters=self._build_filters()
		)


class SlcanCanHardware(CanHardware):
	"""Serial-line CAN backend (Windows/python-can)."""

	def _open_socket(self):
		_, channel = self.port.split(":", 1)
		return self._create_socket(
			bustype=CanBackend.SLCAN.value, 
			channel=channel, 
			bitrate=self.bitrate, 
			can_filters=self._build_filters()
		)


class GsUsbCanHardware(CanHardware):
	"""GS-USB/CANable backend (Windows/python-can)."""

	def _open_socket(self):
		_initialize_gs_usb_backend()

		return self._create_socket(
			bustype=CanBackend.GS_USB.value,
			channel=int(self.port.split(":", 1)[1]),
			bitrate=self.bitrate,
			# can-isotp filters by address. Avoid python-can's filtering loop
			# shrinking USB timeouts until they round to an indefinite wait.
			can_filters=None if self._raw else self._build_filters(),
		)


def _initialize_gs_usb_backend() -> None:
	"""Load system libusb or the packaged Windows DLL before gs_usb scans."""
	from usb.backend import libusb1

	if libusb1.get_backend() is not None:
		return
	if platform.startswith("win32"):
			from libusb_package import find_library

			if libusb1.get_backend(find_library=find_library) is not None:
				return
	raise RuntimeError("Unable to load the libusb backend required by GS-USB")


def _available_ports_windows() -> list[HardwarePort]:
	"""Discover Windows PCAN, Vector, SLCAN and GS-USB adapters."""
	ports: list[HardwarePort] = []

	try:
		import can
		configs = can.detect_available_configs()
	except Exception:
		configs = []

	for config in configs:
		interface = config.get("interface")
		channel = config.get("channel")
		if interface not in ("pcan", "vector") or channel is None:
			continue
		if interface == "vector" and getattr(config.get("hw_type"), "name", "") == "XL_HWTYPE_VIRTUAL":
			continue
		if interface == "vector":
			channel = config["channel_index"]

		vector_config = config.get("vector_channel_config")
		port_name = (
			config.get("device_name")
			or getattr(vector_config, "name", None)
			or (f"VN1610 Channel {channel + 1}" if interface == "vector"
				else f"{interface} channel {channel}")
		)
		serial_number = config.get("serial_number")
		if serial_number is None:
			serial_number = config.get("serial")
		ports.append(HardwarePort(
			port=f"{interface}:{channel}",
			port_name=port_name,
			serial_number=str(serial_number) if serial_number is not None else None,
			manufacturer={"pcan": "Peak", "vector": "Vector"}.get(interface),
		))

	try:
		from serial.tools import list_ports
		supported_slcan_devices = {(0xAD50, 0x60C4): "CANable"}
		for device in list_ports.comports():
			manufacturer = supported_slcan_devices.get((device.vid, device.pid))
			if manufacturer is not None:
				ports.append(HardwarePort(
					port=f"slcan:{device.device}",
					port_name=device.device,
					serial_number=device.serial_number,
					manufacturer=manufacturer,
				))
	except Exception:
		pass

	try:
		from can.interfaces.gs_usb import GsUsb
		from usb.util import dispose_resources

		_initialize_gs_usb_backend()
		for channel, adapter in enumerate(GsUsb.scan()):
			try:
				product = adapter.gs_usb.product or "GS-USB"
				manufacturer = adapter.gs_usb.manufacturer or "Unknown"
				serial_number = adapter.gs_usb.serial_number or None
			finally:
				dispose_resources(adapter.gs_usb)
				# This prevents the error "usb.core.USBError: [Errno 13] Access denied (insufficient permissions)"
			ports.append(HardwarePort(
				port=f"gs_usb:{channel}",
				port_name=product,
				serial_number=product,
				manufacturer=manufacturer,
			))

	except Exception as exc:
		print(f"GS-USB discovery failed: {exc}")

	return ports