from abc import ABCMeta
from ..kwp import KWPCommand, KWPResponse, KWPNegativeStatus, KWPNegativeResponseException

class InterfaceABC(metaclass=ABCMeta):
	def init (self) -> None:
		"""Make the bus ready for sending and receiving commands"""

	def execute (self, kwp_command: KWPCommand) -> KWPResponse:
		payload = [kwp_command.command] + kwp_command.data
		
		response = self._execute_internal(payload) # returns list (status, data)

		if (len(response) == 0): # timeout. todo!
			return KWPResponse()

		status = response[0]
		if ( status == (kwp_command.command + 0x40) ): # positive response
			return KWPResponse().set_data(response[1:])
		elif (status == 0x7F): # negative response
			negative_responses = [str(KWPNegativeStatus(code)) for code in response[1:]]
			exception_str = ', '.join(negative_responses)
			raise KWPNegativeResponseException('Negative response', exception_str)
		else: # this probably shouldnt happen? 
			raise Exception('Neither negative, nor positive response. This probably shouldn\'t happen.')

	def shutdown (self) -> None:
		"""Clean up, stop communication, close interfaces"""

	def __del__(self) -> None:
		self.shutdown()

	def __exit__(self) -> None:
		self.shutdown()