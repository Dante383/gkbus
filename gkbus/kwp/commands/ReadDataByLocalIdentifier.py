from ..KWPCommand import KWPCommand

class ReadDataByLocalIdentifier(KWPCommand):
	command = 0x21

	def __init__ (self, data):
		self.data = data