from ..KWPCommand import KWPCommand

class RequestUpload(KWPCommand):
	command = 0x35

	def __init__ (self, data):
		self.data = data