'''
J2534 binding and library discovery - no J2534 library or adapter needed
'''
import ctypes
import dataclasses
import json
import logging
import math
import os
import struct
from collections.abc import Iterator

import pytest

from gkbus.channel import CanFilter, CanFrame, IsoTpParams, KLineTiming
from gkbus.device import Bus, J2534Device, J2534KLineChannel, discovery
from gkbus.device.j2534 import j2534_device, j2534_isotp_link, j2534_kline_channel, registry
from gkbus.device.j2534 import library as j2534_library
from gkbus.device.j2534.constants import (
	CAN_29BIT_ID,
	CAN_ID_BOTH,
	ISO9141_NO_CHECKSUM,
	ISO15765_FRAME_PAD,
	Config,
	FilterType,
	Ioctl,
	Protocol,
	Status,
)
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
	DeviceException,
	OpeningChannelException,
	TimeoutException,
)
from gkbus.transport import Kwp2000OverKLineTransport

from .fakes import FakeJ2534Library


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

# --- device, CAN channel and ISO-TP link, on an adapter faked at the J2534 library level ---

OPENPORT_INFO = registry.J2534LibraryInfo(
	'/usr/local/lib/libj2534.so', 'OpenPort 2.0', 'Tactrix', profile=registry.OPENPORT,
)
GENERIC_INFO = registry.J2534LibraryInfo('/opt/passthru.so', 'Some Box', 'ACME')

@pytest.fixture
def adapter (monkeypatch: pytest.MonkeyPatch) -> FakeJ2534Library:
	'''
	The library J2534Device loads. Answers ISO-TP requests to 0x7E0 from 0x7E8 with the
	request reversed, CAN frames to 0x5A0 from 0x5A1 the same way
	'''
	def ecu (message: J2534Message) -> list[J2534Message]:
		can_id, data = message.data[:4], message.data[4:]
		answer_id = {b'\x00\x00\x07\xE0': 0x7E8, b'\x00\x00\x05\xA0': 0x5A1}.get(can_id)
		if answer_id is None:
			return []
		return [J2534Message(message.protocol, answer_id.to_bytes(4, 'big') + data[::-1])]

	library = FakeJ2534Library(ecu)
	monkeypatch.setattr(j2534_device, 'J2534Library', lambda path: library)
	monkeypatch.setattr(j2534_isotp_link, '_padding_noted', set())
	return library

@pytest.fixture
def openport (adapter: FakeJ2534Library) -> Iterator[J2534Device]:
	device = J2534Device(OPENPORT_INFO)
	yield device
	device.close()

def test_device_open_close (adapter: FakeJ2534Library) -> None:
	device = J2534Device(OPENPORT_INFO)
	assert device.port == 'j2534:OpenPort 2.0'
	assert device.description() == 'J2534 OpenPort 2.0 (Tactrix)'
	with device:
		assert device.open()
		assert adapter.calls_to('open') == [()]
		assert (device.firmware_version, device.library_version, device.api_version) == \
			('1.17.4877', 'fake 1.0', '04.04')
		assert device.description() == 'J2534 OpenPort 2.0 (Tactrix), firmware 1.17.4877'
		assert device.battery_voltage() == pytest.approx(12.48)
	assert not device.is_open() and not adapter.device_open
	device.close()
	assert adapter.calls_to('close') == [(1,)]
	# handle() opens it again
	assert device.handle()[1] == 1 and adapter.device_open
	device.close()

def test_device_opens_without_versions (adapter: FakeJ2534Library) -> None:
	adapter.fail['read_version'] = Status.ERR_FAILED
	device = J2534Device(OPENPORT_INFO)
	device.open()
	assert device.is_open() and device.firmware_version is None
	device.close()

@pytest.mark.parametrize('status, reason', [
	(Status.ERR_DEVICE_NOT_CONNECTED, 'OpenPort 2.0 is not connected'),
	(Status.ERR_DEVICE_IN_USE, 'OpenPort 2.0 is in use by another program'),
	(Status.ERR_FAILED, 'ERR_FAILED'),
])
def test_device_opening_errors (adapter: FakeJ2534Library, status: int, reason: str) -> None:
	adapter.fail['open'] = status
	device = J2534Device(OPENPORT_INFO)
	with pytest.raises(J2534Error, match=reason) as error:
		device.open()
	assert error.value.status == status
	assert not device.is_open()

def test_device_close_failure_is_logged (
	adapter: FakeJ2534Library, caplog: pytest.LogCaptureFixture,
) -> None:
	device = J2534Device(OPENPORT_INFO)
	device.open()
	adapter.fail['close'] = Status.ERR_FAILED
	device.close()
	assert not device.is_open()
	assert 'Closing OpenPort 2.0 failed' in caplog.text

def test_device_needs_a_library (no_libraries: object) -> None:
	with pytest.raises(DeviceException, match='No J2534 library is installed'):
		J2534Device()
	with pytest.raises(DeviceException, match='No J2534 library matching mongoose is installed'):
		J2534Device('mongoose')

def test_device_from_port (monkeypatch: pytest.MonkeyPatch) -> None:
	asked = []
	def find_library (spec: str | None) -> registry.J2534LibraryInfo:
		asked.append(spec)
		return OPENPORT_INFO
	monkeypatch.setattr(j2534_device, 'find_library', find_library)
	assert J2534Device.from_port('can0') is None
	assert J2534Device.from_port('/dev/ttyUSB0') is None
	assert J2534Device.from_port('gs_usb:0') is None
	assert isinstance(J2534Device.from_port('j2534'), J2534Device)
	assert isinstance(J2534Device.from_port('J2534:openport'), J2534Device)
	assert asked == [None, 'openport']

def test_device_discover (
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
	unplugged = OPENPORT_INFO
	unknown = GENERIC_INFO
	wrong_bitness = dataclasses.replace(GENERIC_INFO, path='/opt/other.dll', machine='bogus')
	monkeypatch.setattr(j2534_device, 'find_libraries', lambda: [unplugged, unknown, wrong_bitness])
	monkeypatch.setattr(registry, 'usb_ids', lambda: set())
	monkeypatch.setattr(registry.sys, 'platform', 'linux')
	assert [x.library for x in J2534Device.discover()] == [unknown]
	assert 'this Python can\'t load it' in caplog.text

	monkeypatch.setattr(registry, 'usb_ids', lambda: {(0x0403, 0xCC4D)})
	assert [x.library for x in J2534Device.discover()] == [unplugged, unknown]

def test_device_buses_narrowed_to_the_library (
	adapter: FakeJ2534Library, monkeypatch: pytest.MonkeyPatch,
) -> None:
	can_only = dataclasses.replace(GENERIC_INFO, buses=frozenset({Bus.CANBUS}))
	kline_only = dataclasses.replace(GENERIC_INFO, buses=frozenset({Bus.KLINE}))
	monkeypatch.setattr(j2534_device, 'find_libraries', lambda: [can_only])
	monkeypatch.setattr(discovery, 'DEVICE_TYPES', [J2534Device])
	assert discovery.discover({Bus.KLINE}) == []
	assert [x.buses for x in discovery.discover({Bus.CANBUS})] == [frozenset({Bus.CANBUS})]
	with pytest.raises(ChannelNotSupportedException, match='does not support'):
		J2534Device(kline_only).canbus()
	assert not adapter.device_open

def test_can_filters_installed_once_used (openport: J2534Device, adapter: FakeJ2534Library) -> None:
	channel = openport.canbus()
	channel.open()
	assert adapter.calls_to('connect') == [(Protocol.CAN, CAN_ID_BOTH, 500_000)]
	# a channel only used for ISO-TP doesn't take every frame on the bus
	assert adapter.calls_to('start_filter') == []
	channel.send(CanFrame(0x5A0, b'\x01\x02'))
	assert adapter.channels[5].filters == {1: (FilterType.PASS, bytes(4), bytes(4), None, 0)}
	assert channel.recv(0.1) == CanFrame(0x5A1, b'\x02\x01')
	assert len(adapter.calls_to('start_filter')) == 1

	# reopened: nothing to apply until it's used, filters asked for are applied right away
	channel.close()
	channel.open()
	channel.set_filters(None)
	assert len(adapter.calls_to('start_filter')) == 1
	channel.set_filters([CanFilter.for_id(0x5A1)])
	assert list(adapter.channels[5].filters.values()) == [
		(FilterType.PASS, b'\x00\x00\x07\xFF', b'\x00\x00\x05\xA1', None, 0),
	]

def test_can_filters (openport: J2534Device, adapter: FakeJ2534Library) -> None:
	channel = openport.canbus(filters=[CanFilter.for_id(0x5A1), CanFilter(0x1ABCDE00, 0x1FFFFF00)])
	channel.open()
	assert sorted(adapter.channels[5].filters.values()) == [
		(FilterType.PASS, b'\x00\x00\x07\xFF', b'\x00\x00\x05\xA1', None, 0),
		(FilterType.PASS, b'\x1F\xFF\xFF\x00', b'\x1A\xBC\xDE\x00', None, CAN_29BIT_ID),
	]
	adapter.receive(5, J2534Message(Protocol.CAN, b'\x00\x00\x03\x16\x01'))
	adapter.receive(5, J2534Message(Protocol.CAN, b'\x1A\xBC\xDE\x05\x02', rx_status=CAN_29BIT_ID))
	assert channel.recv(0.1) == CanFrame(0x1ABCDE05, b'\x02', extended=True)

	# replaced while open, and an empty list lets everything through
	channel.set_filters([])
	assert list(adapter.channels[5].filters.values()) == [
		(FilterType.PASS, bytes(4), bytes(4), None, 0),
	]
	adapter.receive(5, J2534Message(Protocol.CAN, b'\x00\x00\x03\x16\x01'))
	assert channel.recv(0.1) == CanFrame(0x316, b'\x01')

def test_can_too_many_filters_for_the_adapter (
	openport: J2534Device, adapter: FakeJ2534Library,
) -> None:
	filters = [CanFilter.for_id(0x5B0 + x) for x in range(11)]
	channel = openport.canbus(filters=filters)
	channel.open()
	assert list(adapter.channels[5].filters.values()) == [
		(FilterType.PASS, bytes(4), bytes(4), None, 0),
	]
	adapter.receive(5, J2534Message(Protocol.CAN, b'\x00\x00\x03\x16\x01'))
	adapter.receive(5, J2534Message(Protocol.CAN, b'\x00\x00\x05\xBA\x02'))
	assert channel.recv(0.1) == CanFrame(0x5BA, b'\x02')

def test_can_own_frames_dropped (openport: J2534Device, adapter: FakeJ2534Library) -> None:
	channel = openport.canbus()
	channel.open()
	channel.send(CanFrame(0x5A2, b'\x01'))
	# the same frame from another node is received
	adapter.receive(5, J2534Message(Protocol.CAN, b'\x00\x00\x05\xA2\x01'))
	channel.send(CanFrame(0x1ABCDE01, b'\x02', extended=True))
	assert adapter.written[-1].tx_flags == CAN_29BIT_ID
	adapter.receive(5, J2534Message(Protocol.CAN, b'\x00\x00\x05\xA3'))
	# transmit indications and our own frames skipped
	assert channel.recv(0.1) == CanFrame(0x5A2, b'\x01')
	assert channel.recv(0.1) == CanFrame(0x5A3, b'')
	with pytest.raises(TimeoutException):
		channel.recv(0.01)

def test_can_send_and_recv_errors (openport: J2534Device, adapter: FakeJ2534Library) -> None:
	channel = openport.canbus()
	with pytest.raises(ChannelException, match='not open'):
		channel.send(CanFrame(0x5A0, b''))
	with pytest.raises(ChannelException, match='not open'):
		channel.recv(0)
	channel.open()
	with pytest.raises(ChannelException, match='too long'):
		channel.send(CanFrame(0x5A0, bytes(9)))
	adapter.fail['write'] = Status.ERR_TIMEOUT
	with pytest.raises(TimeoutException):
		channel.send(CanFrame(0x5A0, b''))
	assert adapter.calls_to('write')[-1] == (5, 200)

def test_can_close_closes_links (
	openport: J2534Device, adapter: FakeJ2534Library, caplog: pytest.LogCaptureFixture,
) -> None:
	channel = openport.canbus()
	channel.open()
	link = channel.isotp(0x7E0, 0x7E8)
	link.open()
	adapter.fail['disconnect'] = Status.ERR_FAILED
	channel.close()
	assert not link.is_open() and not channel.is_open()
	assert 'Closing the J2534 ISO-TP link failed' in caplog.text
	assert 'Closing the J2534 CAN channel failed' in caplog.text
	del adapter.fail['disconnect']
	# reopening starts from scratch
	adapter.channels.clear()
	channel.open()
	assert channel.is_open()

def test_isotp_link (
	openport: J2534Device, adapter: FakeJ2534Library, caplog: pytest.LogCaptureFixture,
) -> None:
	caplog.set_level(logging.INFO)
	channel = openport.canbus()
	channel.open()
	link = channel.isotp(0x7E0, 0x7E8, IsoTpParams(stmin=2, blocksize=8))
	link.open()
	assert adapter.calls_to('connect')[-1] == (Protocol.ISO15765, 0, 500_000)
	assert adapter.channels[6].filters == {1: (
		FilterType.FLOW_CONTROL, b'\xff' * 4, b'\x00\x00\x07\xE8', b'\x00\x00\x07\xE0',
		ISO15765_FRAME_PAD,
	)}
	assert adapter.channels[6].config == {Config.ISO15765_BS: 8, Config.ISO15765_STMIN: 2}
	# the OpenPort can't be asked for 0xCC
	assert caplog.text.count('pads with 0x00') == 1

	payload = bytes(range(20))
	link.send(payload, 0.5)
	assert adapter.written[-1] == J2534Message(
		Protocol.ISO15765, b'\x00\x00\x07\xE0' + payload, tx_flags=ISO15765_FRAME_PAD,
	)
	assert adapter.calls_to('write')[-1] == (6, 500)
	# the transmit indication and the first frame indication carry no payload
	assert link.recv(0.1) == payload[::-1]
	with pytest.raises(TimeoutException):
		link.recv(0.01)
	# raw CAN keeps working alongside
	channel.send(CanFrame(0x5A0, b'\x01\x02'))
	assert channel.recv(0.1) == CanFrame(0x5A1, b'\x02\x01')

	link.close()
	assert 6 not in adapter.channels and channel._links == []
	link.open()
	assert caplog.text.count('pads with 0x00') == 1
	link.close()
	with pytest.raises(ChannelException, match='not open'):
		link.send(b'\x01', 0.1)

def test_isotp_link_29bit_unpadded (openport: J2534Device, adapter: FakeJ2534Library) -> None:
	channel = openport.canbus()
	channel.open()
	link = channel.isotp(0x18DA10F1, 0x18DAF110, IsoTpParams(padding=None))
	link.open()
	assert adapter.calls_to('connect')[-1] == (Protocol.ISO15765, CAN_29BIT_ID, 500_000)
	assert next(iter(adapter.channels[6].filters.values()))[-1] == CAN_29BIT_ID
	link.send(b'\x3E\x00', 0.1)
	assert adapter.written[-1].tx_flags == CAN_29BIT_ID

@pytest.mark.parametrize('pad_value_fails', [False, True])
def test_isotp_padding_byte_configured (
	adapter: FakeJ2534Library, caplog: pytest.LogCaptureFixture, pad_value_fails: bool,
) -> None:
	caplog.set_level(logging.INFO)
	device = J2534Device(GENERIC_INFO)
	channel = device.canbus()
	channel.open()
	if pad_value_fails:
		adapter.fail['set_config'] = Status.ERR_NOT_SUPPORTED
		# BS and STMIN can't fail here, only the padding byte is optional
		original = adapter.set_config
		def set_config (channel_id: int, parameter: int, value: int) -> None:
			if parameter == Config.ISO15765_PAD_VALUE:
				original(channel_id, parameter, value)
			else:
				adapter.channels[channel_id].config[parameter] = value
		adapter.set_config = set_config  # type: ignore[method-assign]
	channel.isotp(0x7E0, 0x7E8).open()
	if pad_value_fails:
		assert 'Some Box can\'t pad ISO-TP frames with 0xCC, it pads with its own byte' \
			in caplog.text
	else:
		assert adapter.channels[6].config[Config.ISO15765_PAD_VALUE] == 0xCC
		assert 'pads with' not in caplog.text
	device.close()

def test_isotp_link_open_errors (openport: J2534Device, adapter: FakeJ2534Library) -> None:
	channel = openport.canbus()
	link = channel.isotp(0x7E0, 0x7E8)
	with pytest.raises(ChannelException, match='CAN channel is not open'):
		link.open()
	channel.open()
	link.open()
	with pytest.raises(OpeningChannelException, match='only one can be at a time'):
		channel.isotp(0x7E1, 0x7E9).open()
	link.close()

	# a link that couldn't be set up is closed again
	adapter.fail['set_config'] = Status.ERR_FAILED
	with pytest.raises(J2534Error):
		link.open()
	assert not link.is_open() and 6 not in adapter.channels

# --- K-Line ---

def kwp_frame (data: bytes, target: int = 0xF1, source: int = 0x10) -> bytes:
	frame = bytes([0x80 + len(data), target, source]) + data
	return frame + bytes([sum(frame) & 0xFF])

def kwp_ecu (message: J2534Message) -> list[J2534Message]:
	'''
	Answers every K-Line request positively with the request's data, in two messages -
	the adapter splits a response wherever the ECU pauses
	'''
	if message.protocol not in FakeJ2534Library.KLINE_PROTOCOLS:
		return []
	data = message.data[3:-1]
	response = kwp_frame(bytes([data[0] + 0x40]) + data[1:])
	return [
		J2534Message(message.protocol, response[:2]),
		J2534Message(message.protocol, response[2:]),
	]

@pytest.fixture
def kline_adapter (adapter: FakeJ2534Library) -> FakeJ2534Library:
	adapter.ecu = kwp_ecu
	return adapter

def test_kline_kwp2000 (openport: J2534Device, kline_adapter: FakeJ2534Library) -> None:
	channel = openport.kline()
	transport = Kwp2000OverKLineTransport(channel, 0x10, 0xF1)
	transport.init(b'\x81')
	assert kline_adapter.calls_to('connect') == [(Protocol.ISO14230, ISO9141_NO_CHECKSUM, 10400)]
	assert kline_adapter.channels[4].filters == {1: (FilterType.PASS, b'\x00', b'\x00', None, 0)}
	assert kline_adapter.channels[4].config == {
		Config.LOOPBACK: 0, Config.P1_MAX: 40, Config.P3_MIN: 120, Config.P4_MIN: 0,
	}
	assert kline_adapter.calls_to('fast_init') == [(4, transport.build_payload(b'\x81'))]

	assert transport.send_read_pdu(b'\x1A\x90') == b'\x5A\x90'
	# the whole frame in one message, checksum and all - nothing echoed
	assert kline_adapter.written[-1].data == transport.build_payload(b'\x1A\x90')
	assert kline_adapter.written[-1].protocol == Protocol.ISO14230
	# P3, 6 bytes at 10400 baud, margin
	assert kline_adapter.calls_to('write')[-1] == (4, math.ceil(60 + 6 * 10 * 1000 / 10400) + 1000)

def test_kline_byte_stream (openport: J2534Device, kline_adapter: FakeJ2534Library) -> None:
	channel = openport.kline()
	channel.open()
	channel.write(kwp_frame(b'\x3E', target=0x10, source=0xF1))
	# across the adapter's messages, leftovers kept for the next read
	assert channel.read(1, 0.1) == b'\x81'
	assert channel.read(3, 0.1) == b'\xF1\x10\x7E'
	assert channel.read(1, 0.1) == bytes([sum(b'\x81\xF1\x10\x7E') & 0xFF])
	# what arrived of a frame that didn't arrive in time is gone, like on a serial port
	channel.write(kwp_frame(b'\x3E', target=0x10, source=0xF1))
	with pytest.raises(TimeoutException):
		channel.read(10, 0.01)
	with pytest.raises(TimeoutException):
		channel.read(1, 0)
	# echoes are consumed
	kline_adapter.channels[4].config[Config.LOOPBACK] = 1
	channel.write(kwp_frame(b'\x3E', target=0x10, source=0xF1))
	assert channel.read(5, 0.1) == kwp_frame(b'\x7E')

	channel.write(kwp_frame(b'\x3E', target=0x10, source=0xF1))
	channel.reset_buffers()
	assert kline_adapter.calls_to('clear_rx_buffer')[-1] == (4,)
	assert kline_adapter.calls_to('clear_tx_buffer')[-1] == (4,)
	with pytest.raises(TimeoutException):
		channel.read(1, 0)

	channel.close()
	assert 4 not in kline_adapter.channels
	with pytest.raises(ChannelException, match='not open'):
		channel.read(1, 0)

def test_kline_fast_init (openport: J2534Device, kline_adapter: FakeJ2534Library) -> None:
	channel = openport.kline()
	channel.open()
	start_communication = kwp_frame(b'\x81', target=0x10, source=0xF1)
	# the response is returned, and never read even if the adapter queued it too
	kline_adapter.fast_init_queues_response = True
	assert channel.fast_init(start_communication) == b'\x81\xF1'
	with pytest.raises(TimeoutException):
		channel.read(1, 0)

	# an ECU not answering is no error
	kline_adapter.ecu = lambda message: []
	assert channel.fast_init(start_communication) == b''
	# the adapter failing is
	kline_adapter.fail['fast_init'] = Status.ERR_FAILED
	with pytest.raises(J2534Error):
		channel.fast_init(start_communication)

def test_kline_set_baudrate (
	openport: J2534Device, kline_adapter: FakeJ2534Library, monkeypatch: pytest.MonkeyPatch,
) -> None:
	sleeps: list[float] = []
	monkeypatch.setattr(j2534_kline_channel.time, 'sleep', sleeps.append)
	channel = openport.kline(baudrate=9600, timing=KLineTiming(p3_min=20))
	channel.set_baudrate(10400)
	channel.open()
	assert kline_adapter.calls_to('connect') == [(Protocol.ISO14230, ISO9141_NO_CHECKSUM, 10400)]

	channel.write(kwp_frame(b'\x10\x85\x14', target=0x10, source=0xF1))
	assert channel.read(7, 0.1)[3:5] == b'\x50\x85'
	# changed on the open channel, like the OpenPort does
	channel.set_baudrate(125_000)
	assert channel.get_baudrate() == 125_000
	assert kline_adapter.channels[4].config[Config.DATA_RATE] == 125_000
	assert kline_adapter.calls_to('disconnect') == []
	assert sleeps == []

	# adapters that can't, reopen the channel at the new rate and set it up like before
	kline_adapter.read_only.add((Protocol.ISO14230, Config.DATA_RATE))
	channel.write(kwp_frame(b'\x3E', target=0x10, source=0xF1))
	assert channel.read(5, 0.1) == kwp_frame(b'\x7E')
	channel.set_baudrate(10400)
	assert kline_adapter.calls_to('disconnect') == [(4,)]
	assert kline_adapter.calls_to('connect')[-1] == (Protocol.ISO14230, ISO9141_NO_CHECKSUM, 10400)
	assert channel.get_baudrate() == 10400
	assert kline_adapter.channels[4].config == {
		Config.LOOPBACK: 0, Config.P1_MAX: 40, Config.P3_MIN: 40, Config.P4_MIN: 0,
	}
	assert len(kline_adapter.channels[4].filters) == 1
	# P3 since the ECU's response kept, the new channel doesn't know about it
	assert len(sleeps) == 1 and 0 < sleeps[0] <= 0.02
	channel.write(kwp_frame(b'\x3E', target=0x10, source=0xF1))
	assert channel.read(5, 0.1) == kwp_frame(b'\x7E')

def test_kline_set_timing (openport: J2534Device, kline_adapter: FakeJ2534Library) -> None:
	channel = openport.kline()
	channel.set_timing(KLineTiming(p1_max=5, p3_min=0.5, p4_min=1))
	assert kline_adapter.calls_to('set_config') == []
	channel.open()
	channel.set_timing(KLineTiming(p1_max=2.5, p3_min=0, p4_min=0))
	assert channel.get_timing() == KLineTiming(p1_max=2.5, p3_min=0, p4_min=0)
	assert [x[1:] for x in kline_adapter.calls_to('set_config')] == [
		(Config.LOOPBACK, 0), (Config.P1_MAX, 10), (Config.P3_MIN, 1), (Config.P4_MIN, 2),
		(Config.P1_MAX, 5), (Config.P3_MIN, 0), (Config.P4_MIN, 0),
	]

def test_kline_pins (openport: J2534Device, kline_adapter: FakeJ2534Library) -> None:
	# the OpenPort's L line, no J2534-2 pin switching
	channel = J2534KLineChannel(openport, pin=ObdPin.L_LINE)
	channel.open()
	assert [x[0] for x in kline_adapter.calls_to('connect')] == [
		Protocol.ISO14230_PS, Protocol.ISO14230_CH2,
	]
	channel.write(kwp_frame(b'\x3E', target=0x10, source=0xF1))
	assert channel.read(5, 0.1) == kwp_frame(b'\x7E')
	channel.close()

	with pytest.raises(ChannelNotSupportedException, match='can\'t do K-Line on OBD pin 9'):
		J2534KLineChannel(openport, pin=ObdPin.PIN_9).open()
	assert kline_adapter.channels == {}

def test_kline_pin_switching (kline_adapter: FakeJ2534Library) -> None:
	'''
	A J2534-2 adapter switches pins, others can't do anything but pin 7
	'''
	device = J2534Device(GENERIC_INFO)
	kline_adapter.channel_ids[Protocol.ISO14230_PS] = 9
	J2534KLineChannel(device, pin=ObdPin.PIN_12).open()
	assert kline_adapter.channels[9].config[Config.J1962_PINS] == 0x0C00

	# switching fails: no other way on a generic adapter
	kline_adapter.read_only.add((Protocol.ISO14230_PS, Config.J1962_PINS))
	kline_adapter.channels.clear()
	with pytest.raises(ChannelNotSupportedException, match='can\'t do K-Line on OBD pin 15'):
		J2534KLineChannel(device, pin=ObdPin.L_LINE).open()
	assert kline_adapter.channels == {}
	device.close()

def test_kline_needs_kline_library (adapter: FakeJ2534Library) -> None:
	can_only = dataclasses.replace(GENERIC_INFO, buses=frozenset({Bus.CANBUS}))
	with pytest.raises(ChannelNotSupportedException, match='does not support kline'):
		J2534Device(can_only).kline()

def test_kline_and_can_together (openport: J2534Device, kline_adapter: FakeJ2534Library) -> None:
	kline, can = openport.kline(), openport.canbus()
	kline.open()
	can.open()
	assert set(kline_adapter.channels) == {4, 5}
	openport.close()
	assert not kline.is_open() and not can.is_open() and not kline_adapter.device_open
