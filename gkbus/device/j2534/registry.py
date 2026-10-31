'''
Finding installed J2534 libraries. Nothing is loaded or opened here
'''

import ctypes.util
import glob
import json
import logging
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import serial.tools.list_ports

from ..device_abc import Bus
from ..obd_pin import ObdPin
from .library import library_machine, python_machine

logger = logging.getLogger(__name__)

#: path of a J2534 library to use, several can be separated with os.pathsep
LIBRARY_ENV = 'GKBUS_J2534_LIBRARY'
#: where J2534 libraries register themselves on Windows
REGISTRY_KEY = r'SOFTWARE\PassThruSupport.04.04'
#: where Linux and macOS J2534 libraries register themselves (OpenVehicleDiag convention)
PASSTHRU_DIR = os.path.join('~', '.passthru')
#: where libraries are installed when they don't register
KNOWN_PATHS = (
	'/usr/local/lib/libj2534.so',
	'/usr/local/lib/libj2534.dylib',
	'/opt/homebrew/lib/libj2534.dylib',
)
USB_DIR = '/sys/bus/usb/devices'

ALL_BUSES = frozenset({Bus.KLINE, Bus.CANBUS})
#: protocols a library can declare, and the bus they need
PROTOCOL_BUSES = {
	'CAN': Bus.CANBUS,
	'ISO15765': Bus.CANBUS,
	'ISO9141': Bus.KLINE,
	'ISO14230': Bus.KLINE,
}


@dataclass(frozen=True)
class AdapterProfile:
	'''
	What gkbus knows about a J2534 adapter beyond what J2534 itself tells

	:param usb_ids: (vendor id, product id) of the adapter, to tell if it's plugged in
	:param kline_pins: OBD pins it's known to do K-Line on
	:param groundable_pins: OBD pins it's known to be able to short to ground
	:param isotp_padding: byte it pads ISO-TP frames with no matter what it's asked for,
		None if the padding byte can be configured
	'''
	name: str
	usb_ids: frozenset[tuple[int, int]] = frozenset()
	kline_pins: frozenset[ObdPin] = frozenset({ObdPin.K_LINE})
	groundable_pins: frozenset[ObdPin] = frozenset({ObdPin.L_LINE})
	isotp_padding: int | None = None

#: any J2534 adapter - J2534-1 only guarantees grounding pin 15
GENERIC = AdapterProfile('J2534')
#: Tactrix OpenPort 2.0, through Tactrix's DLL or openport-j2534. Pins 7, 10 and 15 are grounded by
#: the line drivers; 1, 3, 9, 11, 12 and 13 by the programmable voltage circuit, which some clones
#: leave out - they acknowledge grounding those pins and leave them as they are
OPENPORT = AdapterProfile(
	'OpenPort 2.0',
	usb_ids=frozenset({(0x0403, 0xCC4D)}),
	kline_pins=frozenset({ObdPin.K_LINE, ObdPin.L_LINE}),
	groundable_pins=frozenset({
		ObdPin.PIN_1, ObdPin.PIN_3, ObdPin.PIN_7, ObdPin.PIN_9, ObdPin.PIN_10,
		ObdPin.PIN_11, ObdPin.PIN_12, ObdPin.PIN_13, ObdPin.PIN_15,
	}),
	isotp_padding=0x00,
)
#: lowercase markers in a library's name, vendor or file name, and the adapter they mean.
#: libj2534 is what openport-j2534 installs as
PROFILE_MARKERS: list[tuple[tuple[str, ...], AdapterProfile]] = [
	(('openport', 'tactrix', 'op20pt', 'libj2534'), OPENPORT),
]
#: (vendor id, product id) of the known J2534 adapters, e.g. for serial port discovery to skip
ADAPTER_USB_IDS: frozenset[tuple[int, int]] = frozenset().union(
	*(profile.usb_ids for _, profile in PROFILE_MARKERS)
)

@dataclass(frozen=True)
class J2534LibraryInfo:
	'''
	An installed J2534 library

	:param path: the DLL / shared object
	:param name: the device name it registered with
	:param buses: buses it declared support for
	:param machine: Windows only - architecture of the DLL (x86, x64, arm64), None if unknown
	'''
	path: str
	name: str
	vendor: str = ''
	buses: frozenset[Bus] = ALL_BUSES
	profile: AdapterProfile = field(default=GENERIC, compare=False)
	machine: str | None = None

	@classmethod
	def from_path (
		cls,
		path: str,
		name: str | None = None,
		vendor: str = '',
		buses: frozenset[Bus] = ALL_BUSES,
	) -> 'J2534LibraryInfo':
		'''
		Recognises the adapter from the name, vendor and file name
		'''
		profile = profile_for(name or '', vendor, os.path.basename(path))
		if not name:
			name = profile.name if profile is not GENERIC else os.path.basename(path)
		machine = library_machine(path) if sys.platform == 'win32' else None
		return cls(path, name, vendor, buses, profile, machine)

	def loadable (self) -> bool:
		'''
		False if it's a Windows DLL this Python can't load (32 bit DLL in 64 bit Python
		or the other way round)
		'''
		return self.machine is None or self.machine == python_machine()

	def present (self) -> bool | None:
		'''
		Whether the adapter is plugged in. None if that can't be told without opening it
		'''
		if not self.profile.usb_ids or sys.platform == 'win32':
			return None
		return any(ids in self.profile.usb_ids for ids in usb_ids())

def profile_for (*names: str) -> AdapterProfile:
	text = ' '.join(names).lower()
	for markers, profile in PROFILE_MARKERS:
		if any(marker in text for marker in markers):
			return profile
	return GENERIC

def find_libraries () -> list[J2534LibraryInfo]:
	'''
	Installed J2534 libraries: the GKBUS_J2534_LIBRARY environment variable first, then the
	Windows registry, ~/.passthru/*.json and the usual install paths. A library found
	in several places is listed once
	'''
	found: list[J2534LibraryInfo] = []
	seen: set[str] = set()
	for library in [*_from_env(), *_from_registry(), *_from_passthru_dir(), *_from_known_paths()]:
		key = os.path.normcase(os.path.realpath(library.path))
		if key in seen:
			continue
		seen.add(key)
		found.append(library)
	return _prefer_loadable(found)

def find_library (spec: str | None = None) -> J2534LibraryInfo | None:
	'''
	:param spec: path of a library, or a part of an installed library's name or vendor
		(case insensitive). None or empty - the first installed library
	'''
	if spec and os.path.isfile(spec):
		return J2534LibraryInfo.from_path(spec)
	libraries = find_libraries()
	if not spec:
		return libraries[0] if libraries else None
	wanted = spec.lower()
	for library in libraries:
		if wanted in library.name.lower() or wanted in library.vendor.lower():
			return library
	return None

def usb_ids () -> list[tuple[int, int]]:
	'''
	(vendor id, product id) of connected USB devices - all of them on Linux,
	the ones with a serial port elsewhere
	'''
	if sys.platform.startswith('linux') and os.path.isdir(USB_DIR):
		ids = []
		for device in os.listdir(USB_DIR):
			try:
				with open(os.path.join(USB_DIR, device, 'idVendor')) as vendor, \
						open(os.path.join(USB_DIR, device, 'idProduct')) as product:
					ids.append((int(vendor.read(), 16), int(product.read(), 16)))
			except (OSError, ValueError):
				continue
		return ids
	return [
		(port.vid, port.pid) for port in serial.tools.list_ports.comports()
		if port.vid is not None and port.pid is not None
	]

def _from_env () -> list[J2534LibraryInfo]:
	paths = [x for x in os.environ.get(LIBRARY_ENV, '').split(os.pathsep) if x]
	for path in paths:
		if not os.path.isfile(path):
			logger.warning('{} points to {}, which does not exist'.format(LIBRARY_ENV, path))
	return [J2534LibraryInfo.from_path(x) for x in paths if os.path.isfile(x)]

def _from_registry () -> list[J2534LibraryInfo]:
	libraries = []
	for entry in _registry_entries():
		path = entry.get('FunctionLibrary')
		if not isinstance(path, str) or not path:
			continue
		libraries.append(J2534LibraryInfo.from_path(
			path,
			name=str(entry.get('Name') or ''),
			vendor=str(entry.get('Vendor') or ''),
			buses=_declared_buses(entry),
		))
	return libraries

def _registry_entries () -> list[dict[str, Any]]:
	'''
	Values of every PassThruSupport.04.04 device key, from both the 64 and 32 bit registry views
	'''
	if sys.platform != 'win32':
		return []
	import winreg

	entries = []
	for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
		try:
			root = winreg.OpenKey(
				winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, winreg.KEY_READ | view,
			)
		except OSError:
			continue
		with root:
			for i in range(winreg.QueryInfoKey(root)[0]):
				try:
					with winreg.OpenKey(root, winreg.EnumKey(root, i)) as device:
						values = range(winreg.QueryInfoKey(device)[1])
						entries.append({
							name: value for name, value, _ in
							(winreg.EnumValue(device, j) for j in values)
						})
				except OSError as e:
					logger.debug('Reading a J2534 registry entry failed: {}'.format(e))
	return entries

def _from_passthru_dir () -> list[J2534LibraryInfo]:
	if sys.platform == 'win32':
		return []
	libraries = []
	for config in sorted(glob.glob(os.path.join(os.path.expanduser(PASSTHRU_DIR), '*.json'))):
		try:
			with open(config) as file:
				entry = {str(k).upper(): v for k, v in json.load(file).items()}
		except (OSError, ValueError, AttributeError) as e:
			logger.debug('Reading {} failed: {}'.format(config, e))
			continue
		path = entry.get('FUNCTION_LIB') or entry.get('FUNCTIONLIBRARY')
		if not isinstance(path, str) or not os.path.isfile(path):
			continue
		libraries.append(J2534LibraryInfo.from_path(
			path,
			name=str(entry.get('NAME') or ''),
			vendor=str(entry.get('VENDOR') or ''),
			buses=_declared_buses(entry),
		))
	return libraries

def _from_known_paths () -> list[J2534LibraryInfo]:
	if sys.platform == 'win32':
		return []
	paths = list(KNOWN_PATHS)
	found = ctypes.util.find_library('j2534')
	if found:
		paths.append(found)
	return [J2534LibraryInfo.from_path(x) for x in paths if os.path.isfile(x)]

def _declared_buses (entry: dict[str, Any]) -> frozenset[Bus]:
	'''
	Buses from the protocol flags of a registry or json entry. All of them if none are declared
	'''
	upper = {str(k).upper(): v for k, v in entry.items()}
	declared = [bus for protocol, bus in PROTOCOL_BUSES.items() if protocol in upper]
	if not declared:
		return ALL_BUSES
	return frozenset(bus for protocol, bus in PROTOCOL_BUSES.items() if upper.get(protocol))

def _prefer_loadable (libraries: Iterable[J2534LibraryInfo]) -> list[J2534LibraryInfo]:
	'''
	Drop DLLs this Python can't load when the same device also registered one it can
	(32 and 64 bit registry views)
	'''
	libraries = list(libraries)
	loadable_names = {x.name for x in libraries if x.loadable()}
	return [x for x in libraries if x.loadable() or x.name not in loadable_names]

