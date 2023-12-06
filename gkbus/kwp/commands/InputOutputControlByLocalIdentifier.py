from ..KWPCommand import KWPCommand

class InputOutputControlByLocalIdentifier(KWPCommand):
	command = 0x30

	def __init__ (self, data):
		self.data = data