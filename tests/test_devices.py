import errno
import os
from types import SimpleNamespace

import pyroute2
import pytest
from pyroute2 import NetlinkError
from serial.tools.list_ports_common import ListPortInfo

from gkbus.device import (
	Bus,
	J2534Device,
	ObdPin,
	PythonCanDevice,
	SerialKLineChannel,
	SerialKLineDevice,
	SocketCanChannel,
	SocketCanDevice,
	discover,
	discovery,
	find_device,
)
from gkbus.device.python_can import PythonCanChannel
from gkbus.device.serial import serial_kline_device
from gkbus.device.socketcan import socketcan_device
from gkbus.exceptions import (
	ChannelInUseException,
	ChannelNotSupportedException,
	DeviceException,
	OpeningChannelException,
)


def comport (name: str, vid: int | None = None, pid: int | None = None) -> ListPortInfo:
	port = ListPortInfo('/dev/' + name, skip_link_detection=True)
	port.vid, port.pid = vid, pid
	return port

@pytest.fixture
def can_interfaces (tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> object:
	'''
	Fake /sys/class/net with a CAN interface and an ethernet one
	'''
	for name, link_type in [('can0', '280'), ('eth0', '1')]:
		(tmp_path / name).mkdir()
		(tmp_path / name / 'type').write_text(link_type + '\n')
	monkeypatch.setattr(socketcan_device, 'NET_DIR', str(tmp_path))
	monkeypatch.setattr(socketcan_device, 'platform', 'linux')
	return tmp_path

def test_serial_discover_order (tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
	# ttyS0 is a real UART, ttyS1 a placeholder without one
	for name, uart_type in [('ttyS0', '4'), ('ttyS1', '0')]:
		(tmp_path / name).mkdir()
		(tmp_path / name / 'type').write_text(uart_type + '\n')
	monkeypatch.setattr(serial_kline_device, 'TTY_DIR', str(tmp_path))

	ports = [
		comport('ttyS0'),
		comport('ttyS1'),
		comport('ttyACM0', 0x1234, 0x0001),
		comport('ttyACM1', 0xAD50, 0x60C4),  # slcan CANable
		comport('cu.usbmodem1', 0x0403, 0xCC4D),  # OpenPort on macOS
		comport('ttyUSB1', 0x0403, 0x6001),
		comport('ttyUSB0', 0x0403, 0x6001),
	]
	monkeypatch.setattr('serial.tools.list_ports.comports', lambda: ports)

	assert [x.port for x in SerialKLineDevice.discover()] == [
		'/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyS0',
	]

def test_serial_device_hands_out_unopened_channel () -> None:
	device = SerialKLineDevice('loop://')
	channel = device.kline(baudrate=9600)
	assert isinstance(channel, SerialKLineChannel)
	assert device.is_open() and not channel.is_open()
	assert channel.get_baudrate() == 9600
	with pytest.raises(ChannelNotSupportedException):
		device.canbus()

def test_channel_in_use () -> None:
	device = SerialKLineDevice('loop://')
	channel = device.kline()
	channel.open()
	with pytest.raises(ChannelInUseException):
		device.kline()
	channel.close()
	assert device.kline() is not channel

def test_device_close_closes_channels () -> None:
	device = SerialKLineDevice('loop://')
	channel = device.kline()
	channel.open()
	device.close()
	assert not channel.is_open() and not device.is_open()

def test_serial_kline_pin (caplog: pytest.LogCaptureFixture) -> None:
	'''
	A serial adapter can't switch pins: it says where its K-Line has to go and carries on
	'''
	device = SerialKLineDevice('loop://')
	assert device.kline_pins() == frozenset()
	assert device.kline().pin == ObdPin.K_LINE
	assert caplog.records == []

	channel = device.kline(pin=15)
	assert channel.pin is ObdPin.L_LINE
	assert caplog.messages == [
		'loop:// can\'t switch pins, make sure its K-Line is wired to OBD pin 15',
	]
	for pin in (ObdPin.SIGNAL_GROUND, ObdPin.BATTERY, 17):
		with pytest.raises(ValueError):
			device.kline(pin=pin)

def test_manual_grounding (caplog: pytest.LogCaptureFixture) -> None:
	'''
	A device that can't ground pins asks the user to, and tells them when to stop
	'''
	device = SerialKLineDevice('loop://')
	assert device.groundable_pins() == frozenset()
	assert device.ground_pin(ObdPin.PIN_9) is False
	assert device.is_open()
	assert device.ground_pin(9) is False
	assert caplog.messages == ['Connect OBD pin 9 to ground: loop:// can\'t ground it']
	assert device.grounded_pins == frozenset()

	# K-Line on a pin the user was asked to ground
	with pytest.raises(DeviceException, match='OBD pin 9 is grounded'):
		device.kline(pin=ObdPin.PIN_9)
	with pytest.raises(ValueError, match='OBD pin 16 is battery positive'):
		device.ground_pin(ObdPin.BATTERY)
	with pytest.raises(ValueError, match='OBD pin 4 is ground'):
		device.ground_pin(4)

	caplog.clear()
	device.release_pin(ObdPin.PIN_9)
	device.release_pin(ObdPin.PIN_9)
	device.release_pin(ObdPin.PIN_12)
	assert caplog.messages == ['OBD pin 9 can be disconnected from ground']

	# released on close
	device.ground_pin(ObdPin.PIN_12)
	caplog.clear()
	device.close()
	assert caplog.messages == ['OBD pin 12 can be disconnected from ground']

def test_grounding_pin_of_open_channel () -> None:
	device = SerialKLineDevice('loop://')
	channel = device.kline(pin=ObdPin.L_LINE)
	channel.open()
	with pytest.raises(DeviceException, match='OBD pin 15 is used by the open kline channel'):
		device.ground_pin(ObdPin.L_LINE)
	assert device.ground_pin(ObdPin.K_LINE) is False
	channel.close()
	assert device.ground_pin(ObdPin.L_LINE) is False
	device.close()

def test_grounded_context (caplog: pytest.LogCaptureFixture) -> None:
	device = SerialKLineDevice('loop://')
	device.ground_pin(ObdPin.PIN_9)
	caplog.clear()
	with device.grounded(ObdPin.PIN_9, ObdPin.PIN_12) as manual:
		assert manual == {ObdPin.PIN_9, ObdPin.PIN_12}
		assert caplog.messages == ['Connect OBD pin 12 to ground: loop:// can\'t ground it']
	# pin 9 was grounded before, it stays
	assert caplog.messages[1:] == ['OBD pin 12 can be disconnected from ground']

	caplog.clear()
	with pytest.raises(ValueError), device.grounded(ObdPin.PIN_12, ObdPin.BATTERY):
		pass
	assert caplog.messages[1:] == ['OBD pin 12 can be disconnected from ground']

def test_python_can_from_port () -> None:
	device = PythonCanDevice.from_port('pcan:PCAN_USBBUS1')
	assert device is not None and (device.interface, device.channel) == ('pcan', 'PCAN_USBBUS1')
	channel = device.canbus(bitrate=250_000)
	assert isinstance(channel, PythonCanChannel) and channel.get_bitrate() == 250_000

	for port in ['COM3', '/dev/ttyUSB0', 'loop://', 'pcan:', 'socketcan:can0', 'nope:1']:
		assert PythonCanDevice.from_port(port) is None, port
	with pytest.raises(ValueError):
		PythonCanDevice('nope:1')

def test_python_can_discovers_only_on_windows (monkeypatch: pytest.MonkeyPatch) -> None:
	from gkbus.device.python_can import python_can_device

	monkeypatch.setattr(python_can_device, 'platform', 'linux')
	assert PythonCanDevice.discover() == []

def test_socketcan_discover_and_from_port (can_interfaces: object) -> None:
	assert [x.port for x in SocketCanDevice.discover()] == ['can0']
	assert SocketCanDevice.from_port('eth0') is None
	assert SocketCanDevice.from_port('../can0') is None
	device = SocketCanDevice.from_port('can0')
	assert device is not None
	assert isinstance(device.canbus(), SocketCanChannel)

def test_find_device (can_interfaces: object) -> None:
	assert isinstance(find_device('can0'), SocketCanDevice)
	assert isinstance(find_device('gs_usb:0'), PythonCanDevice)
	assert isinstance(find_device('/dev/ttyUSB0'), SerialKLineDevice)
	# only K-Line wanted - can0 could only be a serial port then
	assert isinstance(find_device('can0', buses={Bus.KLINE}), SerialKLineDevice)
	with pytest.raises(DeviceException):
		find_device('/dev/ttyUSB0', buses={Bus.CANBUS})

def test_discover_lists_j2534_last (monkeypatch: pytest.MonkeyPatch) -> None:
	for device_type in discovery.DEVICE_TYPES:
		found = [SimpleNamespace(type=device_type, buses=device_type.buses)]
		monkeypatch.setattr(device_type, 'discover', lambda found=found: found)
	assert [x.type for x in discover()] == [
		PythonCanDevice, SocketCanDevice, SerialKLineDevice, J2534Device,
	]
	assert [x.type for x in discover({Bus.KLINE})] == [SerialKLineDevice, J2534Device]

def test_find_device_asks_serial_last (monkeypatch: pytest.MonkeyPatch) -> None:
	# J2534 is listed after serial ports, but a serial port would take its port string
	j2534 = SimpleNamespace()
	monkeypatch.setattr(
		J2534Device, 'from_port', lambda port: j2534 if port.startswith('j2534') else None,
	)
	assert find_device('j2534:openport') is j2534

class FakeNetlink:
	'''
	pyroute2.IPRoute with one CAN interface. Without permission, changing the link fails
	like it does for a user without CAP_NET_ADMIN
	'''

	def __init__ (
		self,
		up: bool,
		bitrate: int | None = 500_000,
		kind: str = 'can',
		error: int | None = None,
	) -> None:
		self.up, self.bitrate, self.kind, self.error = up, bitrate, kind, error
		self.changes: list[dict] = []

	def __call__ (self) -> 'FakeNetlink':
		return self

	def __enter__ (self) -> 'FakeNetlink':
		return self

	def __exit__ (self, *args: object) -> None:
		pass

	def link_lookup (self, ifname: str) -> list[int]:
		return [7]

	def get_links (self, index: int) -> list['FakeNetlink']:
		return [self]

	def __getitem__ (self, key: str) -> int:
		assert key == 'flags'
		return 1 if self.up else 0

	def get (self, path: tuple) -> object:
		bittiming = {'bitrate': self.bitrate} if self.bitrate is not None else None
		return {
			('linkinfo', 'kind'): self.kind,
			('linkinfo', 'data', 'can_bittiming'): bittiming,
		}.get(path)

	def link (self, command: str, index: int, **kwargs: object) -> None:
		if self.error is not None:
			raise NetlinkError(self.error, os.strerror(self.error))
		self.changes.append(kwargs)

def open_socketcan (monkeypatch: pytest.MonkeyPatch, netlink: FakeNetlink) -> SocketCanChannel:
	monkeypatch.setattr(pyroute2, 'IPRoute', netlink)
	channel = SocketCanChannel('can0', bitrate=500_000)
	channel.open()
	return channel

def test_socketcan_uses_ready_link_as_is (monkeypatch: pytest.MonkeyPatch) -> None:
	netlink = FakeNetlink(up=True, error=errno.EPERM)
	channel = open_socketcan(monkeypatch, netlink)
	assert channel.is_open()
	# already up at our bitrate - nothing to change, so no permission needed either
	channel.close()
	assert netlink.changes == []

def test_socketcan_uses_ready_vcan_as_is (monkeypatch: pytest.MonkeyPatch) -> None:
	netlink = FakeNetlink(up=True, bitrate=None, kind='vcan', error=errno.EPERM)
	open_socketcan(monkeypatch, netlink).close()

@pytest.mark.parametrize('netlink, expected', [
	(FakeNetlink(up=False), []),
	(FakeNetlink(up=True, bitrate=250_000), [{'state': 'down'}]),
])
def test_socketcan_configures_link (
	monkeypatch: pytest.MonkeyPatch, netlink: FakeNetlink, expected: list[dict],
) -> None:
	channel = open_socketcan(monkeypatch, netlink)
	assert netlink.changes == [
		*expected,
		{'kind': 'can', 'can_bittiming': {'bitrate': 500_000}},
		{'state': 'up'},
	]
	channel.close()
	assert netlink.changes[-1] == {'state': 'down'}

@pytest.mark.parametrize('netlink, message', [
	(FakeNetlink(up=False, error=errno.EPERM), 'can0 is down and gkbus has no permission'),
	(FakeNetlink(up=True, bitrate=250_000, error=errno.EPERM), 'can0 runs at 250000 bit/s'),
	(FakeNetlink(up=True, bitrate=250_000, error=errno.EINVAL), 'Configuring can0 failed'),
])
def test_socketcan_open_fails (
	monkeypatch: pytest.MonkeyPatch, netlink: FakeNetlink, message: str,
) -> None:
	with pytest.raises(OpeningChannelException, match='^' + message):
		open_socketcan(monkeypatch, netlink)
