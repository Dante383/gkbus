from abc import ABCMeta
from ..kwp import KWPCommand, KWPResponse, KWPNegativeStatus, KWPNegativeResponseException

class InterfaceABC(metaclass=ABCMeta):
	def init (self, payload: KWPCommand = None) -> None:
		"""Make the bus ready for sending and receiving commands"""
		self._init([payload.get_command()] + payload.get_data())

	def _init (self, payload: list[int]) -> None:
		"""Make the bus ready for sending and receiving commands"""

	def execute (self, kwp_command: KWPCommand) -> KWPResponse:
		payload = [kwp_command.get_command()] + kwp_command.get_data()
		
		response = self._execute_internal(payload) # returns list (status, data)

		status = response[0]
		if ( status == (kwp_command.get_command() + 0x40) ): # positive response
			return KWPResponse().set_data(response[1:])
		elif (status == 0x7F): # negative response
			negative_responses = [str(KWPNegativeStatus(code)) for code in response[2:]] # second byte will be service identifier
			exception_str = ', '.join(negative_responses)
			raise KWPNegativeResponseException('Negative response', exception_str)
		else:
			raise Exception('Neither negative, nor positive response. This might indicate incorrect baudrate or another communication being active on this bus.')

	def set_timeout (self, timeout: int | None = None):
		"""Set timeout for the underlaying socket. Pass None to use the default value."""

	def shutdown (self) -> None:
		"""Clean up, stop communication, close interfaces"""

	def __del__(self) -> None:
		self.shutdown()

	def __exit__(self) -> None:
		self.shutdown()