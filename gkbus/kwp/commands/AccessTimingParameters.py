from ..KWPCommand import KWPCommand

class AccessTimingParameters(KWPCommand):
	command = 0x83

	def __init__ (self, data):
		self.data = data