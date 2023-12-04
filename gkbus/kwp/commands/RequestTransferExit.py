from ..KWPCommand import KWPCommand

class RequestTransferExit(KWPCommand):
	command = 0x37

	def __init__ (self):
		self.data = []