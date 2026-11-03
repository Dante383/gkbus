import pytest

from gkbus.channel import KLineTiming
from gkbus.protocol import kwp2000
from gkbus.protocol.kwp2000.commands import AccessTimingParameters, StartCommunication, StartDiagnosticSession
from gkbus.protocol.kwp2000.commands import TesterPresent as KeepAlive  # pytest collects Test*
from gkbus.protocol.kwp2000.enums import DiagnosticSession, ResponseType
from gkbus.transport import Kwp2000OverKLineTransport

from .fakes import FakeCanBus, FakeCanChannel, FakeKLineChannel

ECU, TESTER = 0x10, 0xF1
FAST = KLineTiming(p3_min=20)

def kline_frame (data: bytes) -> bytes:
	frame = bytes([0x80 + len(data), TESTER, ECU]) + data
	return frame + bytes([sum(frame) & 0xFF])

RESPONSES = {
	0x81: b'\xC1\xEF\x8F',
	0x10: b'\x50\x81',
	0x3E: b'\x7E',
	0x83: b'\xC3',
}

def kline_bus (
		channel: FakeKLineChannel | None = None,
		responses: dict[int, bytes] = RESPONSES,
	) -> tuple[kwp2000.Kwp2000Protocol, FakeKLineChannel]:
	if channel is None:
		channel = FakeKLineChannel()
	# the request's service identifier follows the 3 byte header
	channel.ecu = lambda request: kline_frame(responses[request[3]])
	bus = kwp2000.Kwp2000Protocol(Kwp2000OverKLineTransport(channel, ECU, TESTER))
	bus.init(StartCommunication())
	return bus, channel

@pytest.mark.parametrize('session', [DiagnosticSession.DEFAULT, DiagnosticSession.FLASH_REPROGRAMMING])
def test_session_change_resets_timing (session: DiagnosticSession) -> None:
	bus, channel = kline_bus()
	channel.set_timing(FAST)

	bus.execute(StartDiagnosticSession(session))

	assert channel.get_timing() == KLineTiming()

def test_session_change_resets_to_creation_timing () -> None:
	custom = KLineTiming(p3_min=80)
	channel = FakeKLineChannel()
	channel.timing = channel.default_timing = custom
	bus, _ = kline_bus(channel)
	channel.set_timing(FAST)

	bus.execute(StartDiagnosticSession(DiagnosticSession.DEFAULT))

	assert channel.get_timing() == custom

def test_session_change_resets_timing_before_sending () -> None:
	bus, channel = kline_bus()
	timings: list[KLineTiming] = []
	def ecu (request: bytes) -> bytes:
		timings.append(channel.get_timing())
		return kline_frame(RESPONSES[request[3]])
	channel.ecu = ecu
	channel.set_timing(FAST)

	bus.execute(StartDiagnosticSession(DiagnosticSession.DEFAULT))

	assert timings == [KLineTiming()]

def test_rejected_session_change_still_resets_timing () -> None:
	bus, channel = kline_bus(responses=RESPONSES | {0x10: b'\x7F\x10\x12'})
	channel.set_timing(FAST)

	with pytest.raises(kwp2000.Kwp2000NegativeResponseException):
		bus.execute(StartDiagnosticSession(DiagnosticSession.DEFAULT))

	assert channel.get_timing() == KLineTiming()

def test_timing_to_defaults_resets_timing () -> None:
	bus, channel = kline_bus()
	channel.set_timing(FAST)

	bus.execute(AccessTimingParameters().set_timing_parameters_to_default_values())

	assert channel.get_timing() == KLineTiming()

@pytest.mark.parametrize('command', [
	KeepAlive(ResponseType.REQUIRED),
	AccessTimingParameters().read_limits_of_possible_timing_parameters(),
	AccessTimingParameters().set_timing_parameters_to_given_values(0, 2, 0, 0xFE, 0),
])
def test_other_commands_keep_timing (command: kwp2000.Kwp2000Command) -> None:
	bus, channel = kline_bus()
	channel.set_timing(FAST)

	bus.execute(command)

	assert channel.get_timing() == FAST

def test_session_change_on_can () -> None:
	class Transport:
		channel = FakeCanChannel(FakeCanBus())
		def init (self, data: bytes) -> None:
			pass
		def send_read_pdu (self, data: bytes) -> bytes:
			return b'\x50\x81'

	bus = kwp2000.Kwp2000Protocol(Transport())
	bus.init(StartCommunication())

	assert bus.execute(StartDiagnosticSession(DiagnosticSession.DEFAULT)).success()
