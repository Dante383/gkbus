from ..KWPCommand import KWPCommand

class SecurityAccess(KWPCommand):
	command = 0x27

	def __init__ (self, data):
		self.data = data