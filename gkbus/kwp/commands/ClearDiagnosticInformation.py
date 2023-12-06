from ..KWPCommand import KWPCommand

class ClearDiagnosticInformation(KWPCommand):
	command = 0x14

	def __init__ (self, data):
		self.data = data