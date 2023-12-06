from ..KWPCommand import KWPCommand

class ResponseOnEvent(KWPCommand):
	command = 0x86

	def __init__ (self, data):
		self.data = data