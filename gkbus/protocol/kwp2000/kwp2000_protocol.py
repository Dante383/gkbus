import logging, threading, time
from typing import Union
from dataclasses import dataclass
from ..protocol_abc import ProtocolABC
from ...transport import Kwp2000OverKLineTransport
from ...hardware import TimeoutException
from .kwp2000_command import Kwp2000Command
from .commands import StartCommunication
from .kwp2000_response import Kwp2000ResponseFrame, Kwp2000Response
from .kwp2000_negative_status import Kwp2000NegativeStatus, Kwp2000NegativeStatusIdentifierEnum

logger = logging.getLogger(__name__)

class Kwp2000Exception(Exception):
	pass

class Kwp2000NegativeResponseException(Exception):
	def __init__ (self, status: Kwp2000NegativeStatus) -> None:
		self.status = status

	def __str__ (self) -> str:
		return '{} - {}'.format(hex(self.status.identifier), self.status.message)
	
	def __repr__ (self) -> str:
		return self.__str__()

@dataclass
class Kwp2000RequestFrame:
	service_identifier: int
	data: bytes

	def to_pdu (self) -> bytes:
		return self.service_identifier.to_bytes(1, 'big') + self.data

class Kwp2000Protocol (ProtocolABC):
	def open (self) -> bool:
		return self.transport.hardware.open()

	def init (self, init_command: Kwp2000Command, keepalive_command: Kwp2000Command = None, keepalive_delay: float = 1.5) -> bool:
		if not isinstance(self.transport, Kwp2000OverKLineTransport):
			return True

		init_payload = Kwp2000RequestFrame(init_command.get_service_identifier(), init_command.get_data(as_list=False))

		try:
			self.transport.hardware.set_timeout(0.4)
			(response, time_low, time_high) = self.transport.init(init_payload.to_pdu())
			logger.debug('K-Line FastInit: success: {}, time low: {}, time high: {}'.format(response, time_low, time_high))
			self.transport.read_pdu()
			self.transport.hardware.set_timeout(2)
		except TimeoutException:
			logger.warning('K-Line fast init failed')

		self.transport.hardware.set_timeout(2)
		self._execute_lock = threading.Lock()

		if keepalive_command:
			self.keepalive_command = keepalive_command
			self.keepalive_delay = keepalive_delay
			self._keepalive_thread = None
			self._last_execution_time = time.time()
			self._keepalive_event = threading.Event()
			self._start_keepalive()

		return True # there should be some error checking - but at this stage its hard to determine whether we succeeded


	def execute (self, command: Kwp2000Command) -> Kwp2000Response:
		frame = Kwp2000RequestFrame(command.get_service_identifier(), command.get_data(as_list=False))

		with self._execute_lock:
			response_pdu = self.transport.send_read_pdu(data=frame.to_pdu())
			self._last_execution_time = time.time()

			response = self.handle_errors(
				Kwp2000Response(Kwp2000ResponseFrame(status=response_pdu[0], data=response_pdu[1:]))
			)

		return response

	def handle_errors (self, response: Kwp2000Response) -> Union[None, Kwp2000Response]:
		if response.success():
			return response

		if response.frame.data[0] == Kwp2000NegativeStatusIdentifierEnum.REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING.value:
			logger.info('ECU is busy, request received, response pending.')

			response_pdu = self.transport.read_pdu()
			self._last_execution_time = time.time()
			return self.handle_errors(Kwp2000Response(Kwp2000ResponseFrame(status=response_pdu[0], data=response_pdu[1:])))

		raise Kwp2000NegativeResponseException(Kwp2000NegativeStatus(identifier=response.frame.data[1]))

	def _keepalive (self):
		'''
		Send the keepalive command if keepalive_delay seconds elapsed since the last transmitted frame
		'''
		try:
			while not self._keepalive_event.is_set():
				time.sleep(1)
				elapsed_time = time.time() - self._last_execution_time if self._last_execution_time else float('inf')
				if elapsed_time >= self.keepalive_delay:
					try:
						self.execute(self.keepalive_command)
					except (TimeoutException, Kwp2000NegativeResponseException, AttributeError):
						break
		except KeyboardInterrupt:
			pass

	def _start_keepalive (self):
		'''
		Start the keep-alive thread
		'''
		self._keepalive_event.clear()
		self._keepalive_thread = threading.Thread(target=self._keepalive)
		self._keepalive_thread.start()

	def _stop_keepalive (self):
		if hasattr(self, '_keepalive_event'):
			self._keepalive_event.set()
		if hasattr(self, '_keepalive_thread'):
			self._keepalive_thread.join()

	def close (self) -> None:
		self._stop_keepalive()
		self.transport.hardware.close()