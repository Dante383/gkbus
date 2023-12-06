from ..KWPCommand import KWPCommand

class RequestRoutineResultsByLocalIdentifier(KWPCommand):
	command = 0x33

	def __init__ (self, data):
		self.data = data