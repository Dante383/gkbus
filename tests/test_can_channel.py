import pytest

from gkbus.channel import CanFilter, CanFrame, IsoTpParams, SoftwareIsoTpLink
from gkbus.exceptions import TimeoutException

from .fakes import FakeCanBus, FakeCanChannel


def test_frame_extended_follows_identifier () -> None:
	assert CanFrame(0x7E0, b'\x01').extended is False
	assert CanFrame(0x18DA10F1, b'\x01').extended is True
	assert CanFrame(0x10, b'\x01', extended=True).extended is True
	assert CanFrame(0x10, bytearray(b'\x01')).data == b'\x01'

def test_filter_matching () -> None:
	assert CanFilter(0x7E8).matches(0x7E8)
	assert not CanFilter(0x7E8).matches(0x7E0)
	assert CanFilter(0x700, 0x700).matches(0x7E8)
	assert CanFilter.for_id(0x18DAF110).can_mask == 0x1FFFFFFF

def test_channel_filters_applied_on_recv () -> None:
	bus = FakeCanBus()
	tester, ecu = FakeCanChannel(bus), FakeCanChannel(bus)
	tester.open()
	ecu.open()
	tester.set_filters([CanFilter(0x7E8)])
	ecu.send(CanFrame(0x123, b'\x00'))
	ecu.send(CanFrame(0x7E8, b'\x01'))
	assert tester.recv(0.1) == CanFrame(0x7E8, b'\x01')
	with pytest.raises(TimeoutException):
		tester.recv(0.05)

@pytest.mark.parametrize('size', [1, 7, 8, 40, 300])
def test_software_isotp_both_directions (size: int) -> None:
	bus = FakeCanBus()
	tester, ecu = FakeCanChannel(bus), FakeCanChannel(bus)
	tester.open()
	ecu.open()
	payload = bytes(x & 0xFF for x in range(size))

	with SoftwareIsoTpLink(tester, 0x7E0, 0x7E8) as tester_link, \
		SoftwareIsoTpLink(ecu, 0x7E8, 0x7E0) as ecu_link:
		tester_link.send(payload, timeout=2)
		assert ecu_link.recv(timeout=2) == payload
		ecu_link.send(payload[::-1], timeout=2)
		assert tester_link.recv(timeout=2) == payload[::-1]

	sent = [frame for frame in bus.frames if frame.identifier == 0x7E0]
	assert all(len(frame.data) == 8 for frame in sent)
	if size == 1:
		assert sent[0].data == b'\x01\x00' + b'\xcc' * 6

def test_software_isotp_without_padding () -> None:
	bus = FakeCanBus()
	tester, ecu = FakeCanChannel(bus), FakeCanChannel(bus)
	tester.open()
	ecu.open()
	with SoftwareIsoTpLink(tester, 0x7E0, 0x7E8, IsoTpParams(padding=None)) as link, \
		SoftwareIsoTpLink(ecu, 0x7E8, 0x7E0) as ecu_link:
		link.send(b'\x3e', timeout=1)
		assert ecu_link.recv(timeout=1) == b'\x3e'
	assert bus.frames[0].data == b'\x01\x3e'

def test_software_isotp_timeouts_and_filters () -> None:
	bus = FakeCanBus()
	tester = FakeCanChannel(bus)
	tester.open()
	tester.set_filters([CanFilter(0x100)])
	link = SoftwareIsoTpLink(tester, 0x7E0, 0x7E8)
	link.open()
	assert tester.get_filters() == [CanFilter(0x7E8)]
	with pytest.raises(TimeoutException):
		link.recv(timeout=0.1)
	with pytest.raises(TimeoutException):
		link.send(bytes(20), timeout=0.3) # multi-frame, nobody sends flow control
	link.close()
	assert tester.get_filters() == [CanFilter(0x100)]
