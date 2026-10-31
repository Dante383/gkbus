import pytest
from serial.tools.list_ports_common import ListPortInfo

from gkbus.device import (
	Bus,
	PythonCanDevice,
	SerialKLineChannel,
	SerialKLineDevice,
	SocketCanChannel,
	SocketCanDevice,
	find_device,
)
from gkbus.device.python_can import PythonCanChannel
from gkbus.device.socketcan import socketcan_device
from gkbus.exceptions import (
	ChannelInUseException,
	ChannelNotSupportedException,
	DeviceException,
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

def test_serial_discover_order (monkeypatch: pytest.MonkeyPatch) -> None:
	ports = [
		comport('ttyS0'),
		comport('ttyACM0', 0x1234, 0x0001),
		comport('ttyACM1', 0xAD50, 0x60C4),  # slcan CANable
		comport('ttyUSB1', 0x0403, 0x6001),
		comport('ttyUSB0', 0x0403, 0x6001),
	]
	monkeypatch.setattr('serial.tools.list_ports.comports', lambda: ports)

	assert [x.port for x in SerialKLineDevice.discover()] == [
		'/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyS0',
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
