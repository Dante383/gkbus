import os
import time
from dataclasses import dataclass
from sys import platform

from scapy.config import conf
from typing_extensions import Self

if platform.startswith('win32'):
	conf.contribs['CANSocket'] = {'use-python-can': True}
	import can
	import usb.core
	import libusb_package
	from gs_usb.gs_usb import GsUsb
	from serial.tools import list_ports

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
	from pyroute2 import IPRoute

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
	can_id: int
	can_mask: int = 0x7ff

class CanHardware(HardwareABC):
	'''
	Hardware class for CAN Bus interfaces. Uses Scapy as a backend.
	'''
	def __init__ (self, port: str, bitrate: int, timeout: int = 1, filters: list[CanFilter] | None = None) -> None:
		self.port: str = port
		self.timeout: float = timeout
		self.filters: list[CanFilter] = filters if filters != None else []
		self.bitrate: int = bitrate

	def _build_filters (self) -> list[dict]:
		'''
		Convert configured CAN filters to the format expected by Scapy.

		'''
		filters = []
		
		for can_filter in self.filters:
			filters.append({'can_id': can_filter.can_id, 'can_mask': can_filter.can_mask})

		if len(filters) == 0:
			filters = None

		return filters

	def open (self) -> bool:
		'''
		Configure the CAN interface and open its Scapy socket.

		Windows uses the selected python-can backend. Linux configures the
		SocketCAN interface and bitrate before opening the socket.

		'''
		# Windows configuration for native USB CAN adapter interfaces.
		try:
			if platform.startswith("win32"):
				interface, channel = self.port.split(":", 1)

				if interface in ("vector", "gs_usb"):
					channel = int(channel)

				elif interface not in ("pcan", "slcan"):
					raise ValueError(
						f"Unsupported CAN interface: {interface}"
					)

				kwargs = {
					"bustype": interface,
					"channel": channel,
					"bitrate": self.bitrate,
					"can_filters": (
						self._build_filters() # Bug with PCAN and GS_USB filtering so i've disabled it. This might be why PCAN is slower too...
						if interface == "vector" # It's possible can filtering isn't present in the firmware itself?
						else None
					),
				}

				if interface == "gs_usb":
					kwargs["backend"] = (
						libusb_package.get_libusb1_backend()
					)

				self.socket = CANSocket(**kwargs)

		# Linux configuration for SocketCAN using IPRoute from pyroute2 to bring up the interface.
			elif platform.startswith('linux'):
				
				with IPRoute() as ipr:
					indexes = ipr.link_lookup(ifname=self.port)

					if not indexes:
						raise RuntimeError(f'CAN interface not found: {self.port}')

					index = indexes[0]
					link = ipr.get_links(index)[0]

					# The bitrate can only be changed while the interface is down.
					if link['flags'] & 1:
						ipr.link('set', index=index, state='down')

					# Configure CAN bitrate using Netlink.
					ipr.link('set', index=index, kind='can', can_bittiming={'bitrate': self.bitrate},)

					# Bring the interface up.
					ipr.link('set', index=index, state='up')

				self.socket = CANSocket(
					channel=self.port,
					can_filters=self._build_filters()
				)

		except (OSError, Scapy_Exception, ValueError) as e:
			raise OpeningPortException(e)

		return True

	def is_open (self) -> bool:
		try:
			return not self.socket.closed
		except (AttributeError, TypeError, ValueError):
			return False

	def read (self, length: int) -> RawFrame:
		try:
			packet = self.socket.sniff(timeout=self.timeout, count=1)[0]
		except IndexError:
			raise TimeoutException

		return RawFrame(identifier=packet.identifier, data=packet.data)

	def write (self, frame: RawFrame) -> int:
		packet = CAN(identifier=frame.identifier, data=frame.data)

		bytes_written = self.socket.send(packet)

		return bytes_written-CAN_HEADER_LEN

	def _read_with_software_filters (self, filters: list, timeout: float = 10.0) -> RawFrame:
		'''
		This should not be used and will be removed soon
		'''
		time_started = time.time()

		while True:
			packet = self.socket.recv()
			can_id = packet.identifier

			for can_filter in filters:
				if (can_id & can_filter['can_mask']) == (can_filter['can_id'] & can_filter['can_mask']):
					return RawFrame(identifier=packet.identifier, data=packet.data)

			if (time.time()-time_started) > timeout:
				raise TimeoutException

	def get_filters (self) -> list[CanFilter]:
		'''
		Get active hardware canbus id filters
		'''
		return self.filters

	def set_filters (self, filters: list[CanFilter]) -> Self:
		'''
		Replace hardware canbus id filters. 
		This will triger a restart of the socket
		'''
		self.filters = filters
		self.close()
		self.open()

	def add_filter (self, can_filter: CanFilter) -> Self:
		'''
		Add new hardware canbus id filter
		This will trigger a restart of the socket
		'''
		self.set_filters(self.get_filters() + can_filter)

	def close (self) -> None:
		if hasattr(self, 'socket'):
			self.socket.close()

	def set_baudrate (self, baudrate: int) -> Self:
		raise NotImplementedError

	def get_baudrate (self) -> int:
		raise NotImplementedError

	def set_timeout (self, timeout: float) -> Self:
		self.socket.timeout = timeout
		self.timeout = timeout
		return self

	@staticmethod
	def _available_ports_linux () -> list[str]:
		'''
		Returns a list of available CAN network interfaces by checking the /sys/class/net/<iface>/type file

		:return: a list containing interface identifiers (can0, vcan0, ...)
		'''
		NET_DIR = '/sys/class/net'
		interfaces: list[str] = []

		if not os.path.exists(NET_DIR):
			return interfaces

		for iface in os.listdir(NET_DIR):
			type_path = os.path.join(NET_DIR, iface, 'type')
			if os.path.isfile(type_path):
				with open(type_path, 'r') as f:
					iface_type = f.read().strip()

				if iface_type == '280':
					interfaces.append(iface)

		return interfaces

	@staticmethod
	def _available_ports_windows () -> list[HardwarePort]:
		"""Discover physical CAN interfaces using python-can."""
		ports = []

		try:
			configs = can.detect_available_configs()
		except Exception as e:
			print(f"CAN discovery failed: {e}")
			return ports

		for config in configs:
			interface = config.get("interface")
			channel = config.get("channel")

			# Only discover the supported physical CAN backends.
			if interface not in ("pcan", "vector") or channel is None:
				continue

			if interface == "vector":
				hw_type = config.get("hw_type")
				hw_type_name = getattr(hw_type, "name", str(hw_type))

				# Ignore Vector virtual channels.
				if hw_type_name == "XL_HWTYPE_VIRTUAL":
					continue

			port = f"{interface}:{channel}"

			vector_config = config.get("vector_channel_config")

			if interface == "vector":
				port_name = (
					f"{config.get('device_name') or getattr(vector_config, 'name', None) or f'VN1610 Channel {channel + 1}'}"
				)
			else:
				port_name = (
					config.get("device_name")
					or getattr(vector_config, "name", None)
					or f"{interface} channel {channel}"
				)

			serial_number = config.get("serial_number")
			if serial_number is None:
				serial_number = config.get("serial")

			ports.append(
				HardwarePort(
					port=port,
					port_name=port_name,
					serial_number=(
						str(serial_number)
						if serial_number is not None
						else None
					),
					manufacturer={
						"pcan": "Peak",
						"vector": "Vector",
					}.get(interface),
				)
			)


		# Discover devices supported by SLCAN.
		try:
			supported_slcan_devices = {
				(0xAD50, 0x60C4): "CANable",
			}

			for device in list_ports.comports():
				vid_pid = (device.vid, device.pid)

				if vid_pid not in supported_slcan_devices:
					continue

				ports.append(
					HardwarePort(
						port=f"slcan:{device.device}",
						port_name=device.device,
						serial_number=device.serial_number,
						manufacturer=supported_slcan_devices[vid_pid],
					)
				)

		except Exception as e:
			print(f"SLCAN discovery failed: {e}")

		# Discover devices supported by gs_usb.
		try:
			backend = libusb_package.get_libusb1_backend()

			devices = list(
				usb.core.find(
					find_all=True,
					backend=backend,
					custom_match=GsUsb.is_gs_usb_device,
				) or []
			)

			for channel, device in enumerate(devices):
				ports.append(
					HardwarePort(
						port=f"gs_usb:{channel}",
						port_name=(
							f"{device.product}"
							f"{device.serial_number} - {device.product}"
						),
						manufacturer=device.manufacturer or "Unknown",
					)
				)
			# This prevents the error "usb.core.USBError: [Errno 13] Access denied (insufficient permissions)"
			del device
			del devices

		except Exception as e:
			print(f"gs_usb discovery failed: {e}")

		return ports


	@staticmethod
	def available_ports () -> list[HardwarePort]:
		if platform.startswith('win32'):
			return CanHardware._available_ports_windows()

		return [
			HardwarePort(port=x, port_name=x)
			for x in CanHardware._available_ports_linux()
		]
