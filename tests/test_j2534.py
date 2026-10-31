'''
J2534 binding and library discovery - no J2534 library or adapter needed
'''
import ctypes
import json
import os
import struct

import pytest

from gkbus.device import Bus
from gkbus.device.j2534 import library as j2534_library
from gkbus.device.j2534 import registry
from gkbus.device.j2534.constants import Ioctl, Status
from gkbus.device.j2534.library import (
	J2534Error,
	J2534Library,
	J2534Message,
	PassThruMsg,
	error_for,
	library_machine,
)
from gkbus.device.obd_pin import ObdPin
from gkbus.exceptions import (
	ChannelException,
	ChannelNotSupportedException,
	OpeningChannelException,
	TimeoutException,
)


def test_passthru_msg_layout () -> None:
	ulong = ctypes.sizeof(ctypes.c_ulong)
	assert PassThruMsg.Data.offset == 6 * ulong
	assert ctypes.sizeof(PassThruMsg) == 6 * ulong + 4128

def test_message_round_trip () -> None:
	message = J2534Message(5, b'\x00\x00\x07\xE0\x01\x02', rx_status=1, tx_flags=0x40, timestamp=7)
	msg = message.to_struct()
	assert msg.DataSize == msg.ExtraDataIndex == 6
	assert J2534Message.from_struct(msg) == message

@pytest.mark.parametrize('status, expected', [
	(Status.ERR_TIMEOUT, TimeoutException),
	(Status.ERR_BUFFER_EMPTY, TimeoutException),
	(Status.ERR_NO_FLOW_CONTROL, TimeoutException),
	(Status.ERR_NOT_SUPPORTED, ChannelNotSupportedException),
	(Status.ERR_INVALID_PROTOCOL_ID, ChannelNotSupportedException),
	(Status.ERR_DEVICE_NOT_CONNECTED, OpeningChannelException),
	(Status.ERR_DEVICE_IN_USE, OpeningChannelException),
	(Status.ERR_FAILED, ChannelException),
	(0x99, ChannelException),
])
def test_error_mapping (status: int, expected: type[Exception]) -> None:
	error = error_for('PassThruX', status, 'details')
	assert isinstance(error, expected)
	assert isinstance(error, J2534Error)
	assert error.status == status
	assert 'PassThruX' in str(error) and 'details' in str(error)

def test_error_names_status () -> None:
	assert str(error_for('PassThruOpen', Status.ERR_DEVICE_IN_USE)) == \
		'PassThruOpen failed: ERR_DEVICE_IN_USE'
	assert 'status 0x99' in str(error_for('PassThruOpen', 0x99))

class FakeDll:
	'''
	Stands in for the ctypes library, records calls and fails with `status` when set
	'''
	def __init__ (self) -> None:
		self.calls: list[tuple[str, tuple]] = []
		self.status = 0
		self.queue: list[J2534Message] = []

	def __getattr__ (self, name: str) -> object:
		def function (*args: object) -> int:
			self.calls.append((name, args))
			handler = getattr(type(self), '_' + name, None)
			if handler is not None:
				return handler(self, *args)
			return self.status
		return function

	def _PassThruGetLastError (self, buffer: ctypes.Array) -> int:
		buffer.value = b'it broke'
		return 0

	def _PassThruReadMsgs (
		self, channel: int, buffer: ctypes.Array, count: object, timeout: int,
	) -> int:
		wanted = count._obj.value
		messages, self.queue = self.queue[:wanted], self.queue[wanted:]
		for i, message in enumerate(messages):
			message.to_struct(buffer[i])
		count._obj.value = len(messages)
		return self.status if messages else Status.ERR_BUFFER_EMPTY

def fake_library () -> tuple[J2534Library, FakeDll]:
	library = J2534Library.__new__(J2534Library)
	library.path = 'fake'
	dll = FakeDll()
	library._dll = dll
	return library, dll

def test_library_raises_with_last_error () -> None:
	library, dll = fake_library()
	dll.status = Status.ERR_DEVICE_IN_USE
	with pytest.raises(OpeningChannelException, match='ERR_DEVICE_IN_USE.*it broke'):
		library.open()

def test_library_read_msgs () -> None:
	library, dll = fake_library()
	assert library.read_msgs(1, 1, 10) == []

	dll.queue = [J2534Message(5, b'\x00\x00\x07\xE8\x01'), J2534Message(5, b'\x00\x00\x07\xE8\x02')]
	assert library.read_msgs(1, 1, 10) == [J2534Message(5, b'\x00\x00\x07\xE8\x01')]
	assert library.read_msgs(1, 5, 10) == [J2534Message(5, b'\x00\x00\x07\xE8\x02')]

def test_library_read_msgs_overflow_keeps_messages (caplog: pytest.LogCaptureFixture) -> None:
	library, dll = fake_library()
	dll.queue = [J2534Message(5, b'\x00\x00\x07\xE8\x01')]
	dll.status = Status.ERR_BUFFER_OVERFLOW
	assert len(library.read_msgs(1, 1, 10)) == 1
	assert 'overran' in caplog.text

def test_library_read_msgs_fails () -> None:
	library, dll = fake_library()
	dll.queue = [J2534Message(5, b'\x00\x00\x07\xE8\x01')]
	dll.status = Status.ERR_DEVICE_NOT_CONNECTED
	with pytest.raises(OpeningChannelException):
		library.read_msgs(1, 1, 10)

def test_library_ioctl_names_the_ioctl () -> None:
	library, dll = fake_library()
	dll.status = Status.ERR_NOT_SUPPORTED
	with pytest.raises(ChannelNotSupportedException, match=r'PassThruIoctl\(SET_CONFIG\)'):
		library.set_config(1, 0x2B, 0xCC)
	name, args = dll.calls[0]
	assert name == 'PassThruIoctl' and args[1] == Ioctl.SET_CONFIG

def test_library_loads_real_library_or_fails_clearly (tmp_path: object) -> None:
	path = tmp_path / 'not-a-library.so'
	path.write_bytes(b'nope')
	with pytest.raises(OpeningChannelException, match='Loading J2534 library'):
		J2534Library(str(path))

@pytest.mark.skipif(not os.path.isfile('/usr/local/lib/libj2534.so'), reason='no libj2534')
def test_library_binds_installed_library () -> None:
	library = J2534Library('/usr/local/lib/libj2534.so')
	assert library.last_error() is not None

def pe_file (path: object, machine: int) -> str:
	header = bytearray(0x40)
	header[:2] = b'MZ'
	struct.pack_into('<I', header, 0x3C, 0x40)
	path.write_bytes(bytes(header) + b'PE\0\0' + struct.pack('<H', machine))
	return str(path)

def test_library_machine (tmp_path: object) -> None:
	assert library_machine(pe_file(tmp_path / 'a.dll', 0x14C)) == 'x86'
	assert library_machine(pe_file(tmp_path / 'b.dll', 0x8664)) == 'x64'
	(tmp_path / 'c.dll').write_bytes(b'garbage')
	assert library_machine(str(tmp_path / 'c.dll')) is None
	assert library_machine(str(tmp_path / 'missing.dll')) is None

def test_library_bitness_mismatch_is_explained (
	tmp_path: object, monkeypatch: pytest.MonkeyPatch,
) -> None:
	path = pe_file(tmp_path / 'op20pt32.dll', 0x14C)
	monkeypatch.setattr(j2534_library.sys, 'platform', 'win32')
	monkeypatch.setattr(j2534_library, 'python_machine', lambda: 'x64')
	monkeypatch.setattr(ctypes, 'WinDLL', lambda path: (_ for _ in ()).throw(OSError('bad image')),
		raising=False)
	with pytest.raises(OpeningChannelException, match='is x86, this Python is x64'):
		J2534Library(path)

@pytest.fixture
def no_libraries (monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> object:
	'''
	Nothing installed: no environment variable, registry, ~/.passthru or known paths
	'''
	monkeypatch.delenv(registry.LIBRARY_ENV, raising=False)
	monkeypatch.setattr(registry, '_registry_entries', lambda: [])
	monkeypatch.setattr(registry, 'PASSTHRU_DIR', str(tmp_path / 'passthru'))
	monkeypatch.setattr(registry, 'KNOWN_PATHS', ())
	monkeypatch.setattr(registry.ctypes.util, 'find_library', lambda name: None)
	return tmp_path

def test_find_libraries_nothing_installed (no_libraries: object) -> None:
	assert registry.find_libraries() == []
	assert registry.find_library() is None

def test_find_libraries_sources_and_dedup (
	no_libraries: object, monkeypatch: pytest.MonkeyPatch,
) -> None:
	tmp_path = no_libraries
	openport = tmp_path / 'libj2534.so'
	other = tmp_path / 'libother.so'
	openport.write_bytes(b'')
	other.write_bytes(b'')
	(tmp_path / 'passthru').mkdir()
	(tmp_path / 'passthru' / 'other.json').write_text(json.dumps({
		'NAME': 'Other Adapter', 'VENDOR': 'Acme', 'FUNCTION_LIB': str(other),
		'CAN': True, 'ISO15765': True, 'ISO14230': False,
	}))
	(tmp_path / 'passthru' / 'broken.json').write_text('{')
	monkeypatch.setenv(registry.LIBRARY_ENV, str(openport))
	monkeypatch.setattr(registry, 'KNOWN_PATHS', (str(openport), str(other)))

	libraries = registry.find_libraries()
	assert [(x.path, x.name) for x in libraries] == [
		(str(openport), 'OpenPort 2.0'),
		(str(other), 'Other Adapter'),
	]
	assert libraries[0].profile is registry.OPENPORT
	assert libraries[1].profile is registry.GENERIC
	assert libraries[1].buses == frozenset({Bus.CANBUS})
	assert registry.find_library('acme') == libraries[1]
	assert registry.find_library('OPENPORT') == libraries[0]
	assert registry.find_library('nothing like it') is None
	assert registry.find_library(str(other)).path == str(other)

def test_find_libraries_windows_registry (
	no_libraries: object, monkeypatch: pytest.MonkeyPatch,
) -> None:
	tmp_path = no_libraries
	monkeypatch.setattr(registry.sys, 'platform', 'win32')
	monkeypatch.setattr(registry, 'python_machine', lambda: 'x64')
	monkeypatch.setattr(registry, '_registry_entries', lambda: [
		{'Name': 'OpenPort 2.0 J2534 ISO/CAN/VPW/PWM', 'Vendor': 'Tactrix Inc.',
			'FunctionLibrary': pe_file(tmp_path / 'op20pt32.dll', 0x14C),
			'CAN': 1, 'ISO15765': 1, 'ISO14230': 1, 'ISO9141': 1},
		{'Name': 'Kline only', 'Vendor': 'Acme',
			'FunctionLibrary': pe_file(tmp_path / 'acme64.dll', 0x8664), 'ISO9141': 1, 'CAN': 0},
		{'Name': 'Kline only', 'Vendor': 'Acme',
			'FunctionLibrary': pe_file(tmp_path / 'acme32.dll', 0x14C), 'ISO9141': 1, 'CAN': 0},
		{'Name': 'No library'},
	])
	libraries = registry.find_libraries()
	# the 32 bit Acme DLL is dropped since there's a 64 bit one, the Tactrix one is kept
	assert [(x.name, x.machine) for x in libraries] == [
		('OpenPort 2.0 J2534 ISO/CAN/VPW/PWM', 'x86'),
		('Kline only', 'x64'),
	]
	assert libraries[0].profile is registry.OPENPORT
	assert not libraries[0].loadable()
	assert libraries[1].buses == frozenset({Bus.KLINE})

def test_library_presence (monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
	for name, ids in [('1-1', ('0403', 'cc4d')), ('1-2', ('1d50', '606f')), ('usb1', None)]:
		(tmp_path / name).mkdir()
		if ids:
			(tmp_path / name / 'idVendor').write_text(ids[0] + '\n')
			(tmp_path / name / 'idProduct').write_text(ids[1] + '\n')
	monkeypatch.setattr(registry, 'USB_DIR', str(tmp_path))
	monkeypatch.setattr(registry.sys, 'platform', 'linux')

	openport = registry.J2534LibraryInfo(
		'/x/libj2534.so', 'OpenPort 2.0', profile=registry.OPENPORT,
	)
	assert openport.present() is True
	assert registry.J2534LibraryInfo('/x/liba.so', 'A').present() is None

	(tmp_path / '1-1' / 'idProduct').write_text('6001\n')
	assert openport.present() is False

def test_obd_pin () -> None:
	assert ObdPin(7) is ObdPin.K_LINE is ObdPin.PIN_7
	assert str(ObdPin.L_LINE) == 'OBD pin 15'
	with pytest.raises(ValueError):
		ObdPin(17)
