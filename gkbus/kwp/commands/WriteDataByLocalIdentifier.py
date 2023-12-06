from ..KWPCommand import KWPCommand

class WriteDataByLocalIdentifier(KWPCommand):
	command = 0x3B

	def __init__ (self, data):
		self.data = data