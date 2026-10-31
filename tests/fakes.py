'''
In-memory channels for tests - no hardware, no python-can
'''
import queue
import time
from collections.abc import Callable

from gkbus.channel import CanChannel, CanFrame, KLineChannel
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
