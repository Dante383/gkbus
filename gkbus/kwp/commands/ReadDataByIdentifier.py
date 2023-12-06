from ..KWPCommand import KWPCommand

class ReadDataByIdentifier(KWPCommand):
	command = 0x22

	def __init__ (self, data):
		self.data = data