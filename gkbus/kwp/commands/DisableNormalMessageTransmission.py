from ..KWPCommand import KWPCommand

class DisableNormalMessageTransmission(KWPCommand):
	command = 0x28

	def __init__ (self, data):
		self.data = data