import itertools
import os
import threading
import time

import can
import pytest

from gkbus.channel import CanFilter, CanFrame, IsoTpParams, SoftwareIsoTpLink
from gkbus.device import KernelIsoTpLink, PythonCanChannel
from gkbus.device.python_can.backends import backend_for
from gkbus.device.socketcan import kernel_isotp_link
from gkbus.exceptions import ChannelException, OpeningChannelException, TimeoutException
from gkbus.transport import CcpOverCanTransport, Kwp2000OverCanTransport

from .fakes import FakeCanBus, FakeCanChannel

TESTER_ID, ECU_ID = 0x7E0, 0x7E8
_virtual_names = itertools.count()

@pytest.fixture
def virtual_pair () -> tuple[PythonCanChannel, PythonCanChannel]:
	name = 'gkbus-test-{}'.format(next(_virtual_names))
	tester = PythonCanChannel('virtual', name)
	ecu = PythonCanChannel('virtual', name)
	tester.open()
	ecu.open()
	yield tester, ecu
	tester.close()
	ecu.close()

def serve (link: SoftwareIsoTpLink, handler: callable, count: int = 1) -> threading.Thread:
	'''
	Answer `count` requests on the ECU side of an ISO-TP link
	'''
	def run () -> None:
		for _ in range(count):
			link.send(handler(link.recv(2)), 2)
	thread = threading.Thread(target=run, daemon=True)
	thread.start()
	return thread

def test_python_can_channel_send_recv_filters (virtual_pair: tuple) -> None:
	tester, ecu = virtual_pair
	tester.set_filters([CanFilter(ECU_ID)])
	ecu.send(CanFrame(0x123, b'\x00'))
	ecu.send(CanFrame(ECU_ID, b'\x01\x02'))
	ecu.send(CanFrame(0x18DAF110, b'\x03'))

	assert tester.recv(0.5) == CanFrame(ECU_ID, b'\x01\x02')
	with pytest.raises(TimeoutException):
		tester.recv(0.05)

	tester.set_filters(None)
	ecu.send(CanFrame(0x18DAF110, b'\x03'))
	assert tester.recv(0.5) == CanFrame(0x18DAF110, b'\x03', extended=True)

def test_python_can_channel_not_open () -> None:
	channel = PythonCanChannel('virtual', 'gkbus-closed')
	with pytest.raises(ChannelException):
		channel.send(CanFrame(1, b''))
	with pytest.raises(ChannelException):
		channel.recv(0.01)
	channel.open()
	channel.close()
	assert not channel.is_open()
	with pytest.raises(ChannelException):
		channel.recv(0.01)

class FakeGsUsbBus:
	'''
	Reads like python-can's gs_usb: the timeout is rounded to whole milliseconds, 0 would
	block forever in libusb. Gives up a bit early, like a rounded down timeout does
	'''

	def __init__ (self, messages: list[can.Message]) -> None:
		self.messages = messages
		self.timeouts_ms: list[int] = []

	def _recv_internal (self, timeout: float | None) -> tuple[can.Message | None, bool]:
		timeout_ms = round(timeout * 1000) if timeout else 1
		self.timeouts_ms.append(timeout_ms)
		assert timeout_ms > 0, 'gs_usb would block forever'
		if self.messages:
			return self.messages.pop(0), False
		time.sleep(timeout_ms / 1000 * 0.9)
		return None, False

	def shutdown (self) -> None:
		pass

def gs_usb_message (identifier: int, data: bytes, is_rx: bool = True) -> can.Message:
	return can.Message(arbitration_id=identifier, data=data, is_extended_id=False, is_rx=is_rx)

def test_gs_usb_recv_never_blocks_forever (monkeypatch: pytest.MonkeyPatch) -> None:
	backend = backend_for('gs_usb')
	bus = FakeGsUsbBus([
		gs_usb_message(TESTER_ID, b'\x01', is_rx=False), # our echo
		gs_usb_message(0x123, b'\x02'), # filtered out
	])
	monkeypatch.setattr(backend, 'before_open', lambda: None)
	monkeypatch.setattr(backend, 'after_close', lambda bus: None)
	monkeypatch.setattr(can, 'Bus', lambda **kwargs: bus)
	channel = PythonCanChannel('gs_usb', '0', filters=[CanFilter.for_id(ECU_ID)])
	channel.open()
	for timeout in (0.0004, 0.0016, 0.02):
		bus.messages.insert(0, gs_usb_message(ECU_ID, b'\x03', is_rx=False))
		with pytest.raises(TimeoutException):
			channel.recv(timeout)
	bus.messages.append(gs_usb_message(ECU_ID, b'\x04'))
	assert channel.recv(0.02) == CanFrame(ECU_ID, b'\x04')
	channel.close()
	assert min(bus.timeouts_ms) == 1

@pytest.mark.parametrize('size', [1, 7, 8, 100, 300])
def test_kwp2000_over_can_end_to_end (virtual_pair: tuple, size: int) -> None:
	tester, ecu = virtual_pair
	transport = Kwp2000OverCanTransport(tester, TESTER_ID, ECU_ID)
	transport.open()
	request = bytes(x & 0xFF for x in range(size))
	with SoftwareIsoTpLink(ecu, ECU_ID, TESTER_ID) as ecu_link:
		thread = serve(ecu_link, lambda data: bytes([data[0] ^ 0x40]) + data[1:])
		response = transport.send_read_pdu(request)
		thread.join(2)
	transport.close()

	assert len(response) == size
	assert response == bytes([request[0] ^ 0x40]) + request[1:]
	# the transport didn't open the channel, so it's left open
	assert tester.is_open()

def test_kwp2000_over_can_timeout (virtual_pair: tuple) -> None:
	tester, _ = virtual_pair
	transport = Kwp2000OverCanTransport(tester, TESTER_ID, ECU_ID, timeout=0.1)
	transport.open()
	with pytest.raises(TimeoutException):
		transport.read_pdu()
	with pytest.raises(TimeoutException):
		transport.read_pdu(timeout=0.05)
	transport.close()

def test_kwp2000_over_can_not_open () -> None:
	transport = Kwp2000OverCanTransport(FakeCanChannel(FakeCanBus()), TESTER_ID, ECU_ID)
	with pytest.raises(ChannelException):
		transport.send_pdu(b'\x3E')

def test_transport_owns_channel_it_opened () -> None:
	channel = FakeCanChannel(FakeCanBus())
	transport = CcpOverCanTransport(channel, TESTER_ID, ECU_ID)
	transport.open()
	assert channel.is_open() and transport.is_open()
	transport.close()
	assert not channel.is_open()

def test_transport_leaves_open_channel_open () -> None:
	channel = FakeCanChannel(FakeCanBus())
	channel.open()
	channel.set_filters([CanFilter(0x100)])

	transport = CcpOverCanTransport(channel, TESTER_ID, ECU_ID)
	transport.open()
	assert channel.get_filters() == [CanFilter.for_id(ECU_ID)]
	transport.close()

	assert channel.is_open()
	assert channel.get_filters() == [CanFilter(0x100)]
	assert channel.open_count == 1

def test_transport_reopens_when_channel_closed_under_it () -> None:
	channel = FakeCanChannel(FakeCanBus())
	transport = CcpOverCanTransport(channel, TESTER_ID, ECU_ID)
	transport.open()
	channel.close()
	assert not transport.is_open()
	transport.open()
	assert transport.is_open() and channel.open_count == 2

def test_transport_releases_channel_if_link_fails () -> None:
	class BrokenLinkTransport(CcpOverCanTransport):
		def _open_link (self) -> None:
			raise ChannelException('nope')

	channel = FakeCanChannel(FakeCanBus())
	transport = BrokenLinkTransport(channel, TESTER_ID, ECU_ID)
	with pytest.raises(ChannelException):
		transport.open()
	assert not channel.is_open() and not transport.is_open()

def test_ccp_crm_only () -> None:
	bus = FakeCanBus()
	tester, ecu = FakeCanChannel(bus), FakeCanChannel(bus)
	ecu.open()
	transport = CcpOverCanTransport(tester, TESTER_ID, ECU_ID, crm_only=True, timeout=0.2)
	transport.open()

	ecu.send(CanFrame(ECU_ID, b'\x01\x02\x03\x04'))  # DAQ
	ecu.send(CanFrame(ECU_ID, b'\xFF\x00'))  # too short
	ecu.send(CanFrame(ECU_ID, b'\xFF\x00\x07\x00\x00\x00\x00\x00'))
	assert transport.read_pdu() == b'\xFF\x00\x07\x00\x00\x00\x00\x00'
	with pytest.raises(TimeoutException):
		transport.read_pdu(timeout=0.05)

def test_ccp_send () -> None:
	bus = FakeCanBus()
	transport = CcpOverCanTransport(FakeCanChannel(bus), TESTER_ID, ECU_ID)
	transport.open()
	assert transport.send_pdu(b'\x01\x00\x01') == 3
	assert bus.frames == [CanFrame(TESTER_ID, b'\x01\x00\x01')]

def test_isotp_params_reach_the_link () -> None:
	channel = FakeCanChannel(FakeCanBus())
	params = IsoTpParams(padding=None, stmin=5)
	transport = Kwp2000OverCanTransport(channel, TESTER_ID, ECU_ID, isotp_params=params)
	transport.open()
	assert transport._link is not None and transport._link.params == params
	transport.close()
	assert transport._link is None

def test_kernel_isotp_link_without_kernel_support (monkeypatch: pytest.MonkeyPatch) -> None:
	class NoIsoTpSocket:
		flags = kernel_isotp_link.isotp.socket.flags

		def __init__ (self) -> None:
			raise OSError(93, 'Protocol not supported')

	monkeypatch.setattr(kernel_isotp_link.isotp, 'socket', NoIsoTpSocket)
	link = KernelIsoTpLink('vcan0', TESTER_ID, ECU_ID)
	with pytest.raises(OpeningChannelException):
		link.open()
	assert not link.is_open()

vcan0 = pytest.mark.skipif(
	not os.path.exists('/sys/class/net/vcan0'),
	reason='needs vcan0: sudo modprobe vcan && sudo ip link add vcan0 type vcan '
		'&& sudo ip link set vcan0 up',
)

@vcan0
@pytest.mark.parametrize('size', [1, 7, 8, 100, 300])
def test_kernel_isotp_link (size: int) -> None:
	payload = bytes(x & 0xFF for x in range(size))
	with KernelIsoTpLink('vcan0', TESTER_ID, ECU_ID) as tester, \
			KernelIsoTpLink('vcan0', ECU_ID, TESTER_ID) as ecu:
		tester.send(payload, 1)
		assert ecu.recv(1) == payload
		ecu.send(payload, 1)
		assert tester.recv(1) == payload

@vcan0
def test_kernel_isotp_link_timeout () -> None:
	with KernelIsoTpLink('vcan0', TESTER_ID, ECU_ID) as tester:
		with pytest.raises(TimeoutException):
			tester.recv(0.05)
