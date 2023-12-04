from ..KWPCommand import KWPCommand

class ECUReset(KWPCommand):
	command = 0x11

	def __init__ (self, data):
		self.data = data