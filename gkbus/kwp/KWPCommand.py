class KWPCommand:
	command: int = 0x0

	def __init__ (self, data: list[int]=[]):
		self.data: list[int] = data

	def set_data (self, data):
		self.data = data
		return self

class KWPCommandWithSubservices(KWPCommand):
	def __init__ (self, subservice: int, *kwargs):
		self.subservice: Enum = subservice
		self.data: list[int] = [subservice.value]
		handler = getattr(self, self.subservices[subservice])
		handler(*kwargs)

	def set_data (self, data: list[int]):
		self.data = [self.subservice.value] + data
		return self