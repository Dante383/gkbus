from ..KWPCommand import KWPCommand

class TesterPresent(KWPCommand):
	command = 0x3E

	def __init__ (self, data):
		self.data = data