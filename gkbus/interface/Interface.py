from abc import ABCMeta
from ..kwp import KWPCommand, KWPResponse, KWPNegativeStatus, KWPNegativeResponseException
import threading, time

class InterfaceABC(metaclass=ABCMeta):
	def init (self, payload: KWPCommand = None, keepalive_payload: KWPCommand = None, keepalive_timeout: int = None) -> None:
		"""Make the bus ready for sending and receiving commands"""
		self._init([payload.get_command()] + payload.get_data())
		self._execute_lock = threading.Lock()

		if (keepalive_payload):
			self.keepalive_payload = keepalive_payload
			self.keepalive_timeout = keepalive_timeout
			self._keepalive_thread = None 
			self._last_execution_time = time.time()
			self._keepalive_event = threading.Event()
			self.start_keepalive()

	def _init (self, payload: list[int]) -> None:
		"""Make the bus ready for sending and receiving commands"""

	def execute (self, kwp_command: KWPCommand) -> KWPResponse:
		"""Send KWPCommand and prepare response"""
		if (not hasattr(self, '_execute_lock')):
			self._execute_lock = threading.Lock() # not ideal 

		with self._execute_lock:
			payload = [kwp_command.get_command()] + kwp_command.get_data()
			
			response = self._execute_internal(payload) # returns list (status, data)
			self._last_execution_time = time.time()

			status = response[0]
			if ( status == (kwp_command.get_command() + 0x40) ): # positive response
				return KWPResponse().set_data(response[1:])
			elif (status == 0x7F): # negative response
				negative_responses = [str(KWPNegativeStatus(code)) for code in response[2:]] # second byte will be service identifier
				exception_str = ', '.join(negative_responses)
				raise KWPNegativeResponseException('Negative response', exception_str)
			else:
				raise Exception('Neither negative, nor positive response. This might indicate incorrect baudrate or another communication being active on this bus.')

	def _keepalive (self):
		"""Send keepalive payload if keepalive_timeout elapsed since last command"""
		try:
			while not self._keepalive_event.is_set():
				elapsed_time = time.time() - self._last_execution_time if self._last_execution_time else float('inf')
				if elapsed_time >= self.keepalive_timeout:
					self.execute(self.keepalive_payload)
				time.sleep(1)
		except KeyboardInterrupt:
			pass

	def set_timeout (self, timeout: int | None = None):
		"""Set timeout for the underlaying socket. Pass None to use the default value."""

	def shutdown (self) -> None:
		"""Clean up, stop communication, close interfaces"""
		self.stop_keepalive()

	def start_keepalive(self):
		"""Start the keep-alive thread."""
		self._keepalive_event.clear()
		self._keepalive_thread = threading.Thread(target=self._keepalive)
		self._keepalive_thread.start()

	def stop_keepalive(self):
		"""Stop the keep-alive thread."""
		if hasattr(self, '_keepalive_event'):
			self._keepalive_event.set()
		if hasattr(self, '_keepalive_thread'):
			self._keepalive_thread.join()

	def __del__(self) -> None:
		self.stop_keepalive()
		self.shutdown()

	def __exit__(self) -> None:
		self.stop_keepalive()
		self.shutdown()