from typing_extensions import Self


class CcpCommand:
	code = 0x0

	def __init__ (self, *args, **kwargs) -> None:
		self.parameters: dict = dict(enumerate(args)) | kwargs
		self.init(*args, **kwargs)

	def init (self, *args, **kwargs):
		if len(args) == 0:
			self.data = bytes()
		else:
			self.data = args[0]
			
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

	def get_parameters (self) -> dict:
		'''
		Get parameters the command was initialized with

		:return: A dictionary of parameters name-value
		'''
		return self.parameters

	def __str__ (self) -> str:
		return 'CCPCommand(code={}, data={}|{})'.format(
			hex(self.get_code()), 
			' '.join([hex(x) for x in list(self.get_data())]),
			', '.join(f'{k}={v}' for k, v in self.get_parameters().items())
			)

	def __repr__ (self) -> str:
		return self.__str__()