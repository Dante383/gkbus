import pytest

from gkbus.device import SerialKLineChannel
from gkbus.exceptions import ChannelException, TimeoutException
from gkbus.transport import Kwp2000OverKLineTransport, PacketDirection

from .fakes import FakeKLineChannel

ECU, TESTER = 0x10, 0xF1

def kline_frame (data: bytes, target: int = TESTER, source: int = ECU) -> bytes:
	'''
	Frame as the ECU would send it
	'''
	header = bytes([0x80 + len(data), target, source]) if len(data) < 127 \
		else bytes([0x80, target, source, len(data)])
	frame = header + data
	return frame + bytes([sum(frame) & 0xFF])

def echo_ecu (response: bytes) -> FakeKLineChannel:
	return FakeKLineChannel(ecu=lambda request: kline_frame(response))

def test_build_payload_short () -> None:
	transport = Kwp2000OverKLineTransport(FakeKLineChannel(), ECU, TESTER)
	assert transport.build_payload(b'\x81') == bytes([0x81, ECU, TESTER, 0x81, 0x03])

def test_build_payload_long () -> None:
	transport = Kwp2000OverKLineTransport(FakeKLineChannel(), ECU, TESTER)
	data = bytes(200)
	payload = transport.build_payload(data)
	assert payload[:4] == bytes([0x80, ECU, TESTER, 200])
	assert payload[4:-1] == data
	assert payload[-1] == sum(payload[:-1]) & 0xFF

@pytest.mark.parametrize('size', [1, 5, 126, 127, 200, 255])
def test_send_read_pdu (size: int) -> None:
	response = bytes(x & 0xFF for x in range(0x40, 0x40 + size))
	channel = echo_ecu(response)
	transport = Kwp2000OverKLineTransport(channel, ECU, TESTER)
	transport.open()

	assert transport.send_read_pdu(b'\x1A\x90') == response
	assert channel.written == [transport.build_payload(b'\x1A\x90')]
	assert [x.direction for x in transport.buffer_dump()] == \
		[PacketDirection.OUTGOING, PacketDirection.INCOMING]

def test_read_pdu_timeouts () -> None:
	channel = FakeKLineChannel()
	transport = Kwp2000OverKLineTransport(channel, ECU, TESTER, timeout=2.5)
	transport.open()

	with pytest.raises(TimeoutException):
		transport.read_pdu()
	with pytest.raises(TimeoutException):
		transport.read_pdu(timeout=0.1)
	transport.set_timeout(3)
	with pytest.raises(TimeoutException):
		transport.read_pdu()

	assert [timeout for _, timeout in channel.reads] == [2.5, 0.1, 3]

def test_init_fast_init_and_drain () -> None:
	channel = echo_ecu(b'\xC1\xEF\x8F')
	transport = Kwp2000OverKLineTransport(channel, ECU, TESTER)

	transport.init(b'\x81')

	assert transport.is_open()
	assert channel.fast_inits == [transport.build_payload(b'\x81')]
	# fast init response isn't waiting in the fake, so the drain stops at the first timeout
	assert channel.reads == [(4, 0.4)]

def test_init_without_pdu_only_opens () -> None:
	channel = FakeKLineChannel()
	transport = Kwp2000OverKLineTransport(channel, ECU, TESTER)
	assert transport.init()
	assert channel.is_open()
	assert channel.fast_inits == []

def test_serial_channel_consumes_echo () -> None:
	channel = SerialKLineChannel('loop://')
	with channel:
		assert channel.write(b'\x81\x10\xF1\x81\x03') == 5
		# the loopback only echoed - nothing else is waiting
		with pytest.raises(TimeoutException):
			channel.read(1, 0.05)

def test_serial_channel_fast_init_returns_input () -> None:
	channel = SerialKLineChannel('loop://')
	with channel:
		payload = b'\x81\x10\xF1\x81\x03'
		assert channel.fast_init(payload) == payload

def test_serial_channel_not_open () -> None:
	channel = SerialKLineChannel('loop://')
	with pytest.raises(ChannelException):
		channel.read(1, 0.01)

def test_serial_channel_baudrate_live () -> None:
	channel = SerialKLineChannel('loop://', baudrate=10400)
	channel.set_baudrate(9600)
	with channel:
		assert channel._port().baudrate == 9600
		channel.set_baudrate(19200)
		assert channel._port().baudrate == 19200
		assert channel.get_baudrate() == 19200
