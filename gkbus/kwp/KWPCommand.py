class KWPCommand:
	command: int = 0x0

	def __init__ (self, data: list[int]=[]):
		self.data: list[int] = data

	def set_data (self, data):
		self.data = data
		return self