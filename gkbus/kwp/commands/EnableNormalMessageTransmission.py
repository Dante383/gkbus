from ..KWPCommand import KWPCommand

class EnableNormalMessageTransmission(KWPCommand):
	command = 0x29

	def __init__ (self, data):
		self.data = data