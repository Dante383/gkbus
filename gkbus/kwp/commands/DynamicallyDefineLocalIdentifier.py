from ..KWPCommand import KWPCommand

class DynamicallyDefineLocalIdentifier(KWPCommand):
	command = 0x2C

	def __init__ (self, data):
		self.data = data