'''
In-memory channels and adapters for tests - no hardware, no python-can
'''
import queue
import time
from collections import deque
from collections.abc import Callable
from typing import ClassVar

from gkbus.channel import CanChannel, CanFrame, KLineChannel
from gkbus.device.j2534.constants import (
	CAN_29BIT_ID,
	CAN_ID_SIZE,
	SHORT_TO_GROUND,
	START_OF_MESSAGE,
	TX_DONE,
	TX_MSG_TYPE,
	VOLTAGE_OFF,
	FilterType,
	Protocol,
	Status,
)
from gkbus.device.j2534.library import J2534Message, error_for
from gkbus.exceptions import ChannelException, TimeoutException


class FakeCanBus:
	'''
	Wire connecting FakeCanChannels - whatever one sends, the others receive
	'''
	def __init__ (self) -> None:
		self.channels: list[FakeCanChannel] = []
		self.frames: list[CanFrame] = []

class FakeCanChannel(CanChannel):
	def __init__ (self, bus: FakeCanBus) -> None:
		super().__init__()
		self.bus = bus
		self.bus.channels.append(self)
		self._queue: queue.Queue[CanFrame] = queue.Queue()
		self._open = False
		self.open_count = 0

	def open (self) -> None:
		if not self._open:
			self._open = True
			self.open_count += 1

	def is_open (self) -> bool:
		return self._open

	def close (self) -> None:
		self._open = False

	def send (self, frame: CanFrame) -> None:
		if not self._open:
			raise ChannelException('not open')
		self.bus.frames.append(frame)
		for channel in self.bus.channels:
			if channel is not self and channel.is_open():
				channel._queue.put(frame)

	def recv (self, timeout: float) -> CanFrame:
		if not self._open:
			raise ChannelException('not open')
		deadline = time.monotonic() + timeout
		while True:
			try:
				frame = self._queue.get(timeout=max(deadline - time.monotonic(), 0))
			except queue.Empty:
				raise TimeoutException from None
			if self._matches_filters(frame):
				return frame

class FakeKLineChannel(KLineChannel):
	'''
	K-Line with an ECU on the other end. `ecu` gets every written payload and returns
	the bytes it answers with
	'''
	def __init__ (self, ecu: Callable[[bytes], bytes] = lambda data: b'') -> None:
		super().__init__()
		self.ecu = ecu
		self.written: list[bytes] = []
		self.fast_inits: list[bytes] = []
		self.reads: list[tuple[int, float]] = []
		self._input = bytearray()
		self._open = False

	def open (self) -> None:
		self._open = True

	def is_open (self) -> bool:
		return self._open

	def close (self) -> None:
		self._open = False

	def read (self, size: int, timeout: float) -> bytes:
		self.reads.append((size, timeout))
		if len(self._input) < size:
			self._input.clear()
			raise TimeoutException
		data = bytes(self._input[:size])
		del self._input[:size]
		return data

	def write (self, data: bytes) -> int:
		self.written.append(data)
		self._input += self.ecu(data)
		return len(data)

	def set_baudrate (self, baudrate: int) -> None:
		self.baudrate = baudrate

	def reset_buffers (self) -> None:
		self._input.clear()

	def fast_init (self, payload: bytes) -> bytes:
		self.fast_inits.append(payload)
		self.ecu(payload)
		return b''

class FakeJ2534Channel:
	def __init__ (self, protocol: int, flags: int, baudrate: int) -> None:
		self.protocol, self.flags, self.baudrate = protocol, flags, baudrate
		#: filter id: (type, mask, pattern, flow control, flags)
		self.filters: dict[int, tuple[int, bytes, bytes, bytes | None, int]] = {}
		self.config: dict[int, int] = {}
		self.queue: deque[J2534Message] = deque()

	def passes (self, data: bytes) -> bool:
		return any(
			kind in (FilterType.PASS, FilterType.FLOW_CONTROL)
			and all(d & m == p & m for d, m, p in zip(data, mask, pattern, strict=False))
			for kind, mask, pattern, _, _ in self.filters.values()
		)

class FakeJ2534Library:
	'''
	J2534Library with an OpenPort-like adapter behind it: firmware channel numbers are the
	channel ids, filters are byte masks and raw CAN frames we send come back through an open
	filter, like on a real bus. `ecu` gets every written message and returns the messages
	it answers with. Set fail[function name] to a status to make that function fail
	'''

	CHANNEL_IDS: ClassVar[dict[int, int]] = {
		Protocol.ISO9141: 3, Protocol.ISO14230: 4, Protocol.CAN: 5, Protocol.ISO15765: 6,
		Protocol.ISO14230_CH2: 8,
	}

	def __init__ (
		self,
		ecu: Callable[[J2534Message], list[J2534Message]] = lambda message: [],
	) -> None:
		self.path = 'fake'
		self.ecu = ecu
		self.calls: list[tuple] = []
		self.fail: dict[str, int] = {}
		self.device_open = False
		self.channels: dict[int, FakeJ2534Channel] = {}
		self.written: list[J2534Message] = []
		self.grounded: set[int] = set()
		self._filter_ids = 0

	def _call (self, name: str, *args: object) -> None:
		self.calls.append((name, *args))
		if name in self.fail:
			raise error_for(name, self.fail[name])

	def _channel (self, name: str, channel_id: int) -> FakeJ2534Channel:
		if channel_id not in self.channels:
			raise error_for(name, Status.ERR_INVALID_CHANNEL_ID)
		return self.channels[channel_id]

	def calls_to (self, name: str) -> list[tuple]:
		return [x[1:] for x in self.calls if x[0] == name]

	def open (self, name: str | None = None) -> int:
		self._call('open')
		if self.device_open:
			raise error_for('PassThruOpen', Status.ERR_DEVICE_IN_USE)
		self.device_open = True
		return 1

	def close (self, device_id: int) -> None:
		self._call('close', device_id)
		self.device_open = False
		self.channels.clear()
		self.grounded.clear()

	def connect (self, device_id: int, protocol: int, flags: int, baudrate: int) -> int:
		self._call('connect', protocol, flags, baudrate)
		if protocol not in self.CHANNEL_IDS:
			raise error_for('PassThruConnect', Status.ERR_INVALID_PROTOCOL_ID)
		channel_id = self.CHANNEL_IDS[protocol]
		if channel_id in self.channels:
			raise error_for('PassThruConnect', Status.ERR_CHANNEL_IN_USE)
		self.channels[channel_id] = FakeJ2534Channel(protocol, flags, baudrate)
		return channel_id

	def disconnect (self, channel_id: int) -> None:
		self._call('disconnect', channel_id)
		self._channel('PassThruDisconnect', channel_id)
		del self.channels[channel_id]

	def read_msgs (self, channel_id: int, count: int, timeout_ms: int) -> list[J2534Message]:
		channel = self._channel('PassThruReadMsgs', channel_id)
		if not channel.queue and timeout_ms:
			time.sleep(timeout_ms / 1000)
		messages: list[J2534Message] = []
		while channel.queue and len(messages) < count:
			messages.append(channel.queue.popleft())
		return messages

	def write_msgs (self, channel_id: int, messages: list[J2534Message], timeout_ms: int) -> None:
		self._call('write', channel_id, timeout_ms)
		channel = self._channel('PassThruWriteMsgs', channel_id)
		for message in messages:
			self.written.append(message)
			wide = message.tx_flags & CAN_29BIT_ID
			if channel.protocol in (Protocol.CAN, Protocol.ISO15765):
				indication = TX_MSG_TYPE | TX_DONE | wide
				channel.queue.append(J2534Message(
					channel.protocol, message.data[:CAN_ID_SIZE], rx_status=indication,
				))
			if channel.protocol == Protocol.CAN:
				# our own frame, seen on the bus
				self.receive(channel_id, J2534Message(Protocol.CAN, message.data, rx_status=wide))
			for answer in self.ecu(message):
				self.receive(channel_id, answer)

	def receive (self, channel_id: int, message: J2534Message) -> None:
		'''
		A message arrives from the bus, the channel's filters decide if it's kept
		'''
		channel = self.channels[channel_id]
		if not channel.passes(message.data):
			return
		if channel.protocol == Protocol.ISO15765 and len(message.data) > CAN_ID_SIZE + 7:
			channel.queue.append(J2534Message(
				message.protocol, message.data[:CAN_ID_SIZE], rx_status=START_OF_MESSAGE,
			))
		channel.queue.append(message)

	def start_msg_filter (
		self,
		channel_id: int,
		filter_type: int,
		mask: J2534Message,
		pattern: J2534Message,
		flow_control: J2534Message | None = None,
	) -> int:
		self._call('start_filter', channel_id, filter_type)
		channel = self._channel('PassThruStartMsgFilter', channel_id)
		if len(channel.filters) >= 10:
			raise error_for('PassThruStartMsgFilter', Status.ERR_EXCEEDED_LIMIT)
		self._filter_ids += 1
		flags = flow_control.tx_flags if flow_control is not None else mask.tx_flags
		channel.filters[self._filter_ids] = (
			filter_type, mask.data, pattern.data,
			flow_control.data if flow_control is not None else None, flags,
		)
		return self._filter_ids

	def stop_msg_filter (self, channel_id: int, filter_id: int) -> None:
		self._call('stop_filter', channel_id, filter_id)
		del self._channel('PassThruStopMsgFilter', channel_id).filters[filter_id]

	def set_programming_voltage (self, device_id: int, pin: int, voltage: int) -> None:
		self._call('set_programming_voltage', pin, voltage)
		if voltage == SHORT_TO_GROUND:
			self.grounded.add(pin)
		elif voltage == VOLTAGE_OFF:
			self.grounded.discard(pin)

	def read_version (self, device_id: int) -> tuple[str, str, str]:
		self._call('read_version')
		return '1.17.4877', 'fake 1.0', '04.04'

	def last_error (self) -> str:
		return ''

	def get_config (self, channel_id: int, parameter: int) -> int:
		self._call('get_config', channel_id, parameter)
		return self._channel('GET_CONFIG', channel_id).config.get(parameter, 0)

	def set_config (self, channel_id: int, parameter: int, value: int) -> None:
		self._call('set_config', channel_id, parameter, value)
		self._channel('SET_CONFIG', channel_id).config[parameter] = value

	def read_vbatt (self, device_id: int) -> int:
		self._call('read_vbatt')
		return 12_480

	def clear_rx_buffer (self, channel_id: int) -> None:
		self._call('clear_rx_buffer', channel_id)
		self._channel('CLEAR_RX_BUFFER', channel_id).queue.clear()

	def clear_tx_buffer (self, channel_id: int) -> None:
		self._call('clear_tx_buffer', channel_id)
