from ..KWPCommand import KWPCommand

class WriteDataByIdentifier(KWPCommand):
	command = 0x2E

	def __init__ (self, data):
		self.data = data