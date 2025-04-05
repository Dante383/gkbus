from typing_extensions import Self

class CcpCommand:
	code = 0x0

	def __init__ (self, data: bytes = bytes()) -> None:
		self.data: bytes = data

	def set_data (self, data: bytes = bytes()) -> Self:
		self.data = data
		return self

	def get_data (self) -> bytes:
		return self.data

	def set_code (self, code: int) -> Self:
		self.code = code
		return self

	def get_code (self) -> int:
		return self.code

	def __str__ (self) -> str:
		return 'CCPCommand(code={}, data={})'.format(hex(self.get_code()), ' '.join([hex(x) for x in list(self.get_data())]))

	def __repr__ (self) -> str:
		return self.__str__()