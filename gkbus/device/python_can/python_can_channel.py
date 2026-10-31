import time
from threading import Lock
from typing import Any

import can

from ...channel import CanChannel, CanFilter, CanFrame
from ...exceptions import ChannelException, OpeningChannelException, TimeoutException
from .backends import backend_for

#: python-can and driver errors that mean the bus couldn't be opened
OPENING_ERRORS = (can.CanError, OSError, ValueError, RuntimeError, ImportError)
#: errors of a bus that's broken or was shut down under us
BUS_ERRORS = (can.CanError, OSError, ValueError)

class PythonCanChannel(CanChannel):
	'''
	CAN bus through any python-can interface (pcan, vector, slcan, gs_usb, virtual, ...)
	'''

	def __init__ (
		self,
		interface: str,
		channel: str,
		bitrate: int = 500_000,
		filters: list[CanFilter] | None = None,
	) -> None:
		'''
		:param interface: python-can interface, for example pcan or gs_usb
		:param channel: python-can channel, for example PCAN_USBBUS1 or 0
		'''
		super().__init__(bitrate, filters)
		self.interface = interface
		self.channel = channel
		self._backend = backend_for(interface)
		self._bus: can.BusABC | None = None
		self._opened = False
		self._lock = Lock()

	def open (self) -> None:
		with self._lock:
			if self._opened:
				return
			self._open()
			self._opened = True

	def is_open (self) -> bool:
		return self._opened

	def close (self) -> None:
		# a reader thread and the user may close the same channel concurrently
		with self._lock:
			if not self._opened:
				return
			self._opened = False
			try:
				self._shutdown_bus()
			finally:
				self._close()

	def send (self, frame: CanFrame) -> None:
		try:
			self._get_bus().send(can.Message(
				arbitration_id=frame.identifier,
				is_extended_id=bool(frame.extended),
				data=frame.data,
			))
		except BUS_ERRORS as e:
			raise ChannelException(e) from e

	def recv (self, timeout: float) -> CanFrame:
		bus = self._get_bus()
		deadline = time.monotonic() + timeout
		while True:
			remaining = deadline - time.monotonic()
			if remaining <= 0:
				raise TimeoutException
			try:
				message = self._backend.recv(bus, remaining)
			except BUS_ERRORS as e:
				raise ChannelException(e) from e
			if message is None or message.is_error_frame or message.is_remote_frame:
				continue
			frame = CanFrame(
				message.arbitration_id, bytes(message.data), message.is_extended_id
			)
			if self._matches_filters(frame):
				return frame

	def _open (self) -> None:
		'''
		Open the bus right away, so a missing adapter shows up here and not on the first send
		'''
		self._create_bus()

	def _close (self) -> None:
		'''
		Hook called after the bus was shut down
		'''

	def _get_bus (self) -> can.BusABC:
		if not self._opened:
			raise ChannelException('CAN channel {} is not open'.format(self._name()))
		bus = self._bus
		if bus is None:
			with self._lock:
				if not self._opened:
					raise ChannelException('CAN channel {} was closed'.format(self._name()))
				bus = self._bus or self._create_bus()
		return bus

	def _create_bus (self) -> can.BusABC:
		try:
			self._backend.before_open()
			self._bus = can.Bus(
				interface=self.interface,
				bitrate=self.bitrate,
				**self._backend.bus_kwargs(self.channel),
				**self._bus_filters(),
			)
		except OPENING_ERRORS as e:
			raise OpeningChannelException(e) from e
		return self._bus

	def _bus_filters (self) -> dict[str, Any]:
		'''
		Filters handed to python-can when creating the bus. None by default - recv() filters
		frames itself, so every backend gets the same filtering
		'''
		return {}

	def _shutdown_bus (self) -> None:
		if self._bus is None:
			return
		bus, self._bus = self._bus, None
		try:
			bus.shutdown()
		finally:
			self._backend.after_close(bus)

	def _name (self) -> str:
		return '{}:{}'.format(self.interface, self.channel)
