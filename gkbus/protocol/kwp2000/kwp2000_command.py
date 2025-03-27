from typing_extensions import Self
from typing import Union

class Kwp2000Command:
	service_identifier: int = 0x0

	def __init__ (self, data: Union[bytes, list[int]]=bytes()) -> None:
		if (isinstance(data, list)): # @todo: deprecate?
			data = bytes(data)

		self.data: bytes = data

	def set_data (self, data: Union[bytes, list[int]]=bytes()) -> Self:
		if (isinstance(data, list)): # @todo: deprecate?
			data = bytes(data)

		self.data = data
		return self

	def get_data (self, as_list=False) -> bytes:
		if as_list:
			return list(self.data)
		return self.data

	def append_data (self, data: Union[bytes, list[int]]=bytes()) -> Self:
		if (isinstance(data, list)): # @todo: deprecate?
			data = bytes(data)

		self.data += data
		return self

	def set_service_identifier (self, service_identifier: int) -> Self:
		self.service_identifier = service_identifier
		return self

	def get_service_identifier (self) -> int:
		return self.service_identifier

	def __str__ (self) -> str:
		return 'KWPCommand(sid={}, data={})'.format(hex(self.get_service_identifier()), ' '.join([hex(x) for x in self.get_data(as_list=True)]))

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

	def get_data (self, as_list: bool = False) -> bytes:
		'''
		Get command payload, with subservice identifier being the first byte
		'''
		if as_list: # @todo: deprecate?
			return list(self.data)

		return self.data

	def __str__ (self) -> str:
		return 'KWPSubservice(sid={}, sub={}, data={})'.format(
			hex(self.get_service_identifier()), 
			hex(self.get_subservice_identifier()),
			' '.join([hex(x) for x in self.get_data(as_list=True)])
		)
