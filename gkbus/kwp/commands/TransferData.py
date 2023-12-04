from ..KWPCommand import KWPCommand

class TransferData(KWPCommand):
	command = 0x36

	def __init__ (self, data):
		self.data = data