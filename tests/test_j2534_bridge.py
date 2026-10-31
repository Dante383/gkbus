'''
The 32 bit J2534 helper and the bridge to it. Runs the helper built for this machine against
a fake J2534 library (tests/j2534_fake.c), and the shipped Windows helper under Wine.
Needs a C compiler; the Wine test needs wine and mingw-w64
'''
import ctypes
import gc
import logging
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from gkbus.channel import CanFrame
from gkbus.device import J2534Device
from gkbus.device.j2534 import bridge, j2534_device, registry
from gkbus.device.j2534.bridge import J2534BridgeLibrary
from gkbus.device.j2534.constants import Ioctl, Protocol, Status
from gkbus.device.j2534.library import (
	J2534Error,
	J2534Library,
	J2534Message,
	SByteArray,
)
from gkbus.exceptions import ChannelException, OpeningChannelException, TimeoutException

TESTS = Path(__file__).parent
FAKE_SOURCE = TESTS / 'j2534_fake.c'
HELPER_SOURCE = Path(bridge.HELPER).parent / 'j2534_helper.c'
FORCE_STATUS = 0x10000
CC = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')

pytestmark = pytest.mark.skipif(
	sys.platform == 'win32' or CC is None, reason='needs a C compiler and dlopen',
)

def compile_c (*arguments: str | Path) -> None:
	assert CC is not None
	subprocess.run([CC, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', *arguments], check=True)

@pytest.fixture(scope='session')
def built (tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
	'''
	The helper and the fake library, built for this machine
	'''
	directory = tmp_path_factory.mktemp('j2534_bridge')
	helper, fake = directory / 'helper', directory / 'libfake_j2534.so'
	libraries = ['-ldl'] if sys.platform.startswith('linux') else []
	compile_c('-o', helper, HELPER_SOURCE, *libraries)
	compile_c('-shared', '-fPIC', '-fvisibility=hidden', '-o', fake, FAKE_SOURCE)
	return helper, fake

@pytest.fixture
def fake (built: tuple[Path, Path], tmp_path: Path) -> str:
	'''
	A fresh copy of the fake, so loading it in this process starts it from scratch
	'''
	path = tmp_path / 'libfake_j2534.so'
	shutil.copy(built[1], path)
	return str(path)

@pytest.fixture
def helper (built: tuple[Path, Path]) -> list[str]:
	return [str(built[0])]

@pytest.fixture
def fake_log (tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
	path = tmp_path / 'fake.log'
	monkeypatch.setenv('J2534_FAKE_LOG', str(path))
	return path

@pytest.fixture(params=['in process', 'bridged'])
def library (
	request: pytest.FixtureRequest, fake: str, helper: list[str],
) -> Iterator[J2534Library]:
	'''
	The fake, loaded both ways - the bridge has to behave like J2534Library
	'''
	loaded = J2534Library(fake) if request.param == 'in process' else \
		J2534BridgeLibrary(fake, command=helper)
	yield loaded
	loaded.unload()

@pytest.fixture
def bridged (fake: str, helper: list[str]) -> Iterator[J2534BridgeLibrary]:
	loaded = J2534BridgeLibrary(fake, command=helper)
	yield loaded
	loaded.unload()

def force_status (library: J2534Library, status: int) -> None:
	'''
	Make the fake's next call return `status`
	'''
	library.ioctl(0, FORCE_STATUS, ctypes.c_ulong(status))

def byte_array (data: bytes, size: int | None = None) -> SByteArray:
	buffer = (ctypes.c_ubyte * (size or len(data)))(*data)
	array = SByteArray(len(data) if size is None else size, buffer)
	array._buffer = buffer  # type: ignore[attr-defined]
	return array

# --- both ways ---

def test_open_close (library: J2534Library) -> None:
	device_id = library.open()
	assert device_id == 1
	assert library.read_version(device_id) == ('1.17.4877', 'fake 1.0', '04.04')
	assert library.connect(device_id, Protocol.ISO14230, 0, 10400) == Protocol.ISO14230 + 100
	library.disconnect(Protocol.ISO14230 + 100)
	library.close(device_id)
	with pytest.raises(J2534Error) as error:
		library.close(7)
	assert error.value.status == Status.ERR_INVALID_DEVICE_ID
	assert 'no such device' in str(error.value)

def test_write_read (library: J2534Library) -> None:
	channel_id = library.connect(library.open(), Protocol.CAN, 0, 500_000)
	big = bytes(range(256)) * 16 + bytes(32)
	sent = [
		J2534Message(Protocol.CAN, b'\x00\x00\x07\xE0\x01\x02', rx_status=3, tx_flags=0x100),
		J2534Message(Protocol.ISO15765, big, tx_flags=0x40),
		J2534Message(Protocol.CAN, b''),
	]
	library.write_msgs(channel_id, sent, 100)
	received = library.read_msgs(channel_id, 2, 100) + library.read_msgs(channel_id, 5, 100)
	assert [x.timestamp for x in received] == [1, 2, 3]
	for message, original in zip(received, sent, strict=True):
		assert (message.protocol, message.data, message.rx_status, message.tx_flags) == \
			(original.protocol, original.data, original.rx_status, original.tx_flags)
	assert len(received[1].data) == 4128

def test_read_nothing (library: J2534Library) -> None:
	channel_id = library.connect(library.open(), Protocol.CAN, 0, 500_000)
	assert library.read_msgs(channel_id, 4, 0) == []
	start = time.monotonic()
	assert library.read_msgs(channel_id, 1, 120) == []
	assert 0.1 < time.monotonic() - start < 1

def test_read_overflow_keeps_messages (
	library: J2534Library, caplog: pytest.LogCaptureFixture,
) -> None:
	channel_id = library.connect(library.open(), Protocol.CAN, 0, 500_000)
	library.write_msgs(channel_id, [J2534Message(Protocol.CAN, b'\x00\x00\x01\x00')] * 2, 0)
	force_status(library, Status.ERR_BUFFER_OVERFLOW)
	with caplog.at_level(logging.WARNING):
		assert len(library.read_msgs(channel_id, 4, 100)) == 2
	assert 'receive queue overran' in caplog.text

def test_read_error (library: J2534Library) -> None:
	channel_id = library.connect(library.open(), Protocol.CAN, 0, 500_000)
	force_status(library, Status.ERR_DEVICE_NOT_CONNECTED)
	with pytest.raises(J2534Error) as error:
		library.read_msgs(channel_id, 1, 0)
	assert error.value.status == Status.ERR_DEVICE_NOT_CONNECTED
	assert 'fake failed with 0x08' in str(error.value)

def test_errors (library: J2534Library) -> None:
	with pytest.raises(OpeningChannelException, match='the fake is busy'):
		library.open('busy')
	assert library.last_error() == 'the fake is busy'
	device_id = library.open('fake')
	with pytest.raises(J2534Error, match='voltage too high for pin 2') as error:
		library.set_programming_voltage(device_id, 2, 0xFFFFFFFE)
	assert error.value.status == 0x77
	library.set_programming_voltage(device_id, 9, 0xFFFFFFFE)
	with pytest.raises(J2534Error, match=r'PassThruIoctl\(0x1234\).*unknown ioctl') as error:
		library.ioctl(0, 0x1234)
	assert error.value.status == Status.ERR_INVALID_IOCTL_ID

def test_config (library: J2534Library) -> None:
	channel_id = library.connect(library.open(), Protocol.ISO14230, 0, 10400)
	assert library.get_config(channel_id, 0x0C) == 0x18
	library.set_config(channel_id, 0x0C, 0xDEADBEEF)
	assert library.get_config(channel_id, 0x0C) == 0xDEADBEEF
	force_status(library, Status.ERR_INVALID_CHANNEL_ID)
	with pytest.raises(J2534Error, match=r'GET_CONFIG') as error:
		library.get_config(channel_id, 0x0C)
	assert error.value.status == Status.ERR_INVALID_CHANNEL_ID

def test_ioctls (library: J2534Library) -> None:
	device_id = library.open()
	channel_id = library.connect(device_id, Protocol.ISO14230, 0, 10400)
	assert library.read_vbatt(device_id) == 12345
	voltage = ctypes.c_ulong()
	library.ioctl(device_id, Ioctl.READ_PROG_VOLTAGE, None, voltage)
	assert voltage.value == 8000
	assert library.fast_init(channel_id, J2534Message(Protocol.ISO14230, b'\x81\x11\xF1')) == \
		b'\xF1\x11\x81'

	address, key_bytes = byte_array(b'\x33'), byte_array(bytes(8))
	library.ioctl(channel_id, Ioctl.FIVE_BAUD_INIT, address, key_bytes)
	assert key_bytes.NumOfBytes == 2
	assert bytes(key_bytes.BytePtr[:2]) == b'\x08\xCC'
	with pytest.raises(J2534Error, match='key byte buffer too small'):
		library.ioctl(channel_id, Ioctl.FIVE_BAUD_INIT, address, byte_array(b'', 1))

	library.write_msgs(channel_id, [J2534Message(Protocol.ISO14230, b'\x01')], 0)
	library.clear_tx_buffer(channel_id)
	library.clear_rx_buffer(channel_id)
	assert library.read_msgs(channel_id, 1, 0) == []

def test_filters (library: J2534Library) -> None:
	channel_id = library.connect(library.open(), Protocol.ISO15765, 0, 500_000)
	mask = J2534Message(Protocol.ISO15765, b'\xFF\xFF\xFF\xFF')
	pattern = J2534Message(Protocol.ISO15765, b'\x00\x00\x07\xE8')
	flow_control = J2534Message(Protocol.ISO15765, b'\x00\x00\x07\xE0')
	assert library.start_msg_filter(channel_id, 1, mask, pattern) == 10
	assert library.start_msg_filter(channel_id, 3, mask, pattern, flow_control) == 31
	library.stop_msg_filter(channel_id, 31)
	with pytest.raises(J2534Error, match='mask and pattern differ in size'):
		library.start_msg_filter(channel_id, 1, mask, J2534Message(Protocol.ISO15765, b'\x00'))

# --- the bridge ---

def test_read_lets_other_calls_through (bridged: J2534BridgeLibrary) -> None:
	'''
	A long read is done in slices, so others don't wait for it, and it returns as soon as
	something arrives
	'''
	device_id = bridged.open()
	channel_id = bridged.connect(device_id, Protocol.CAN, 0, 500_000)
	result: list[object] = []
	reader = threading.Thread(target=lambda: result.append(bridged.read_msgs(channel_id, 1, 3000)))
	start = time.monotonic()
	reader.start()
	time.sleep(0.1)
	assert bridged.read_vbatt(device_id) == 12345
	assert time.monotonic() - start < 0.5
	bridged.write_msgs(channel_id, [J2534Message(Protocol.CAN, b'\x00\x00\x07\xE8\x01')], 0)
	reader.join(2)
	assert time.monotonic() - start < 1
	assert result == [[J2534Message(Protocol.CAN, b'\x00\x00\x07\xE8\x01', timestamp=1)]]

def test_helper_dies (bridged: J2534BridgeLibrary) -> None:
	device_id = bridged.open()
	process = bridged._process
	assert process is not None
	process.kill()
	process.wait()
	with pytest.raises(J2534Error, match='the 32 bit J2534 helper stopped') as error:
		bridged.read_vbatt(device_id)
	assert isinstance(error.value, ChannelException)
	assert error.value.status == Status.ERR_FAILED
	assert bridged.last_error() == ''

def test_unload_closes_the_device (
	fake: str, helper: list[str], fake_log: Path,
) -> None:
	library = J2534BridgeLibrary(fake, command=helper)
	library.open()
	process = library._process
	assert process is not None
	library.unload()
	assert process.returncode == 0
	assert fake_log.read_text().split() == ['open', 'close']
	with pytest.raises(J2534Error, match='the 32 bit J2534 helper is stopped'):
		library.open()
	library.unload()

	# and when it's forgotten
	library = J2534BridgeLibrary(fake, command=helper)
	library.close(library.open())
	library.open()
	process = library._process
	assert process is not None
	del library
	gc.collect()
	assert process.returncode == 0
	assert fake_log.read_text().split() == ['open', 'close'] * 3

@pytest.mark.parametrize('path, reason', [
	('/nonexistent/libj2534.so', 'No such file'),
	('libc.so.6', 'not a J2534 library, it has no PassThru'),
])
def test_load_failures (helper: list[str], path: str, reason: str) -> None:
	if path == 'libc.so.6' and not sys.platform.startswith('linux'):
		pytest.skip('glibc')
	with pytest.raises(OpeningChannelException, match=reason):
		J2534BridgeLibrary(path, command=helper)

def test_helper_missing (fake: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	with pytest.raises(OpeningChannelException, match='Starting the 32 bit J2534 helper'):
		J2534BridgeLibrary(fake, command=[str(tmp_path / 'nothing')])
	monkeypatch.setattr(bridge, 'HELPER', str(tmp_path / 'nothing'))
	assert not bridge.bridge_available()
	with pytest.raises(OpeningChannelException, match='which is missing'):
		J2534BridgeLibrary(fake)

def test_helper_of_another_version (
	fake: str, helper: list[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(bridge, 'VERSION', bridge.VERSION + 1)
	with pytest.raises(OpeningChannelException, match='helper version 1, gkbus asked for 2'):
		J2534BridgeLibrary(fake, command=helper)

def test_malformed_request (bridged: J2534BridgeLibrary) -> None:
	status, _, text = bridged._request('PassThruClose', bridge.Op.CLOSE, b'\x01')
	assert (status, text) == (Status.ERR_FAILED, 'malformed request')
	status, _, text = bridged._request('Nothing', 99, b'')  # type: ignore[arg-type]
	assert status == Status.ERR_FAILED
	assert bridged.open() == 1

def test_load_library (
	fake: str, helper: list[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(bridge, 'HELPER', helper[0])
	monkeypatch.setattr(registry, 'python_machine', lambda: 'x64')
	info = registry.J2534LibraryInfo(fake, 'Fake', machine='x86')
	assert info.bridged() and info.loadable()
	library = bridge.load_library(info)
	assert isinstance(library, J2534BridgeLibrary)
	library.unload()
	library = bridge.load_library(registry.J2534LibraryInfo(fake, 'Fake'))
	assert type(library) is J2534Library

def test_device_through_the_bridge (
	fake: str, helper: list[str], fake_log: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	loaded: list[J2534BridgeLibrary] = []
	def load (info: registry.J2534LibraryInfo) -> J2534BridgeLibrary:
		loaded.append(J2534BridgeLibrary(info.path, command=helper))
		return loaded[-1]
	monkeypatch.setattr(j2534_device, 'load_library', load)

	device = J2534Device(registry.J2534LibraryInfo(fake, 'Fake', 'Fakers'))
	with device:
		assert device.description() == 'J2534 Fake (Fakers), firmware 1.17.4877'
		assert device.battery_voltage() == pytest.approx(12.345)
		channel = device.canbus()
		channel.open()
		with pytest.raises(TimeoutException):
			channel.recv(0.1)
		# the ECU's answer, sent by the fake's loopback
		library, _ = device.handle()
		assert channel._channel_id is not None
		library.write_msgs(channel._channel_id, [
			J2534Message(Protocol.CAN, b'\x00\x00\x07\xE8\x02\x10\x01'),
		], 0)
		assert channel.recv(1) == CanFrame(0x7E8, b'\x02\x10\x01')
		channel.close()
	assert not device.is_open()
	assert fake_log.read_text().split() == ['open', 'close']
	assert len(loaded) == 1 and loaded[0]._process is None

# --- the shipped Windows helper ---

WINE = shutil.which('wine') if shutil.which('winepath') else None
MINGW = shutil.which('i686-w64-mingw32-gcc')

def windows_path (path: Path) -> str:
	return subprocess.run(
		['winepath', '-w', str(path)], check=True, capture_output=True, text=True,
	).stdout.strip()

@pytest.fixture(scope='session')
def fake_dll (tmp_path_factory: pytest.TempPathFactory) -> Path:
	assert MINGW is not None
	path = tmp_path_factory.mktemp('j2534_wine') / 'fake_j2534.dll'
	subprocess.run([
		MINGW, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-static',
		'-Wl,--kill-at', '-o', path, FAKE_SOURCE,
	], check=True)
	return path

@pytest.mark.skipif(WINE is None or MINGW is None, reason='needs wine and mingw-w64')
@pytest.mark.skipif(not bridge.bridge_available(), reason='the helper is not built')
def test_shipped_helper_under_wine (
	fake_dll: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	'''
	The shipped exe with a 32 bit stdcall DLL, like it runs on Windows
	'''
	assert WINE is not None
	log = tmp_path / 'fake.log'
	monkeypatch.setenv('WINEDEBUG', '-all')
	monkeypatch.setenv('J2534_FAKE_LOG', windows_path(log))
	library = J2534BridgeLibrary(windows_path(fake_dll), command=[WINE, bridge.HELPER])
	try:
		run_everything(library)
	finally:
		library.unload()
	assert log.read_text().split() == ['open', 'close', 'open', 'close']

def run_everything (library: J2534Library) -> None:
	device_id = library.open()
	assert library.read_version(device_id) == ('1.17.4877', 'fake 1.0', '04.04')
	channel_id = library.connect(device_id, Protocol.ISO14230, 0, 10400)
	sent = J2534Message(Protocol.ISO14230, bytes(range(256)) * 16 + bytes(32), 3, 0x40)
	library.write_msgs(channel_id, [sent] * 2, 100)
	received = library.read_msgs(channel_id, 4, 100)
	assert [x.data for x in received] == [sent.data] * 2
	assert [(x.rx_status, x.tx_flags, x.timestamp) for x in received] == \
		[(3, 0x40, 1), (3, 0x40, 2)]
	assert library.read_msgs(channel_id, 1, 60) == []
	library.set_config(channel_id, 0x0C, 25)
	assert library.get_config(channel_id, 0x0C) == 25
	assert library.read_vbatt(device_id) == 12345
	request = J2534Message(Protocol.ISO14230, b'\x01\x02')
	assert library.fast_init(channel_id, request) == b'\x02\x01'
	key_bytes = byte_array(bytes(4))
	library.ioctl(channel_id, Ioctl.FIVE_BAUD_INIT, byte_array(b'\x11'), key_bytes)
	assert bytes(key_bytes.BytePtr[:key_bytes.NumOfBytes]) == b'\x08\xEE'
	mask = J2534Message(Protocol.ISO14230, b'\xFF')
	assert library.start_msg_filter(channel_id, 3, mask, mask, mask) == 31
	with pytest.raises(J2534Error, match='voltage too high for pin 2'):
		library.set_programming_voltage(device_id, 2, 0xFFFFFFFE)
	with pytest.raises(OpeningChannelException, match='the fake is busy'):
		library.open('busy')
	library.disconnect(channel_id)
	library.close(device_id)
	# left open: the helper closes it when it's stopped
	library.open()

def test_run_everything_in_process (library: J2534Library) -> None:
	'''
	run_everything() is right, so a failure under Wine is the helper's
	'''
	run_everything(library)

