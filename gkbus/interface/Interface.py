from abc import ABCMeta
from ..kwp.KWPCommand import KWPCommand
from ..kwp.KWPResponse import KWPResponse

class InterfaceABC(metaclass=ABCMeta):
	def init (self) -> None:
		"""Make the bus ready for sending and receiving commands"""

	def execute (self, command: KWPCommand) -> KWPResponse:
		return self._execute_internal(command)

	def shutdown (self) -> None:
		"""Clean up, stop communication, close interfaces"""

	def __del__(self) -> None:
		self.shutdown()

	def __exit__(self) -> None:
		self.shutdown()