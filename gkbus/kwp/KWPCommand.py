from typing import List

class KWPCommand:
	command: int = 0x0

	def __init__ (self, data: List[int]=[]):
		self.data: List[int] = data

	def set_data (self, data):
		self.data = data
		return self

	def get_data (self) -> List[int]:
		return self.data

	def set_command (self, command: int):
		self.command = command
		return self

	def get_command (self) -> int:
		return self.command

	def __str__ (self) -> str:
		return '<KWPCommand: {} {}>'.format(hex(self.get_command()), ' '.join([hex(x) for x in self.get_data()]))

class KWPCommandWithSubservices(KWPCommand):
	def __init__ (self, subservice: int, *kwargs):
		self.subservice: Enum = subservice
		self.data: List[int] = [subservice.value]
		handler = getattr(self, self.subservices[subservice])
		handler(*kwargs)

	def set_data (self, data: List[int]):
		self.data = [self.subservice.value] + data
		return self