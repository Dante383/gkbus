from typing_extensions import Self


class Kwp2000Command:
	service_identifier: int = 0x0

	def __init__ (self, *args: tuple[bytes], **kwargs: dict) -> None:
		self.parameters: dict = dict(enumerate(args)) | kwargs
		self.init(*args, **kwargs)

	def init (self, *args: tuple[bytes], **kwargs: dict) -> None:
		if len(args) == 0:
			self.data = bytes()
		else:
			self.data = args[0]

	def set_data (self, data: bytes=bytes()) -> Self:
		self.data = data

		return self

	def get_data (self) -> bytes:
		return self.data

	def append_data (self, data: bytes=bytes()) -> Self:
		self.data += data
		return self

	def set_service_identifier (self, service_identifier: int) -> Self:
		self.service_identifier = service_identifier
		return self

	def get_service_identifier (self) -> int:
		return self.service_identifier

	def get_parameters (self) -> dict:
		'''
		Get parameters the command was initialized with

		:return: A dictionary of parameters name-value
		'''
		return self.parameters

	def __str__ (self) -> str:
		return '{}(sid={}, data={}|{})'.format(
			type(self).__name__,
			hex(self.get_service_identifier()), 
			' '.join([hex(x) for x in list(self.get_data())]),
			', '.join(f'{k}={hex(v)}' for k, v in self.get_parameters().items())
		)

	def __repr__ (self) -> str:
		return self.__str__()

class Kwp2000CommandWithSubservices(Kwp2000Command):
	def set_subservice_identifier (self, subservice_identifier: int) -> Self:
		'''
		Overwrite the first byte of data with new subservice identifier
		'''
		return self.set_data(bytes([subservice_identifier]) + self.get_data()[1:])

	def get_subservice_identifier (self) -> int:
		return self.get_data()[0]

	def get_data (self) -> bytes:
		'''
		Get command payload, with subservice identifier being the first byte
		'''

		return self.data

	def __str__ (self) -> str:
		return '{}.Subservice(sid={}, sub={}, data={}|{})'.format(
			type(self).__name__,
			hex(self.get_service_identifier()), 
			hex(self.get_subservice_identifier()),
			' '.join([hex(x) for x in list(self.get_data())]),
			', '.join(f'{k}={hex(v)}' for k, v in self.get_parameters().items())
		)
