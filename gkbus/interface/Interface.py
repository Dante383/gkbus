from abc import ABCMeta
from ..kwp.KWPCommand import KWPCommand
from ..kwp.KWPResponse import KWPResponse

class InterfaceABC(metaclass=ABCMeta):
	def init (self) -> None:
		"""Make the bus ready for sending and receiving commands"""

	def execute (self, kwp_command: KWPCommand) -> KWPResponse:
		payload = [kwp_command.command] + kwp_command.data
		
		response = self._execute_internal(payload) # returns list (status, data)

		if (len(response) == 0): # timeout. todo!
			return KWPResponse()

		return KWPResponse().set_status(response[0]).set_data(response[1:])

	def shutdown (self) -> None:
		"""Clean up, stop communication, close interfaces"""

	def __del__(self) -> None:
		self.shutdown()

	def __exit__(self) -> None:
		self.shutdown()