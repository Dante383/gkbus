from abc import abstractmethod
from dataclasses import dataclass

from .channel_abc import ChannelABC


@dataclass(frozen=True)
class KLineTiming:
	'''
	ISO 14230 timing, in milliseconds. Adapters that time the bus themselves (J2534) keep to it;
	serial adapters don't use it yet

	:param p1_max: longest gap between the bytes of an ECU response. The adapter treats a longer
		silence as the end of the response
	:param p3_min: shortest time from the end of an ECU response to the next request. ISO 14230
		says 55 ms, but the SIMK43 ignores requests sent 55 ms after its response at its fast
		baudrates (19531 baud and up), so the default is 60 ms
	:param p4_min: gap between the bytes of a request. ISO 14230 suggests 5 ms; 0 sends
		them back to back like a serial adapter does, which every ECU tested so far accepts
	'''
	p1_max: float = 20.0
	p3_min: float = 60.0
	p4_min: float = 0.0

class KLineChannel(ChannelABC):
	'''
	K-Line - a half duplex byte stream
	'''

	def __init__ (self, baudrate: int = 10400, timing: KLineTiming | None = None) -> None:
		self.baudrate = baudrate
		self.timing = timing if timing is not None else KLineTiming()

	@abstractmethod
	def read (self, size: int, timeout: float) -> bytes:
		'''
		Read exactly `size` bytes

		:param timeout: seconds to wait for all of them
		:raises TimeoutException: fewer than `size` bytes arrived in time
		'''

	@abstractmethod
	def write (self, data: bytes) -> int:
		'''
		Send bytes. Anything the bus echoes back is consumed, it won't show up in read()

		:return: number of bytes written
		'''

	@abstractmethod
	def set_baudrate (self, baudrate: int) -> None:
		'''
		Change the baudrate. Applied immediately if the channel is open, on open otherwise
		'''

	def get_baudrate (self) -> int:
		return self.baudrate

	def set_timing (self, timing: KLineTiming) -> None:
		'''
		Change the bus timing, e.g. after negotiating it with AccessTimingParameters.
		Applied immediately if the channel is open, on open otherwise
		'''
		self.timing = timing

	def get_timing (self) -> KLineTiming:
		return self.timing

	@abstractmethod
	def reset_buffers (self) -> None:
		'''
		Throw away anything waiting in the input and output buffers
		'''

	@abstractmethod
	def fast_init (self, payload: bytes) -> bytes:
		'''
		Wake the bus up with ISO 14230 fast init and send the payload
		(usually a StartCommunication request). Implementations may retry with adjusted timing.
		The input buffer is left empty

		:return: whatever came back during the wake-up, only useful for logging
		'''
