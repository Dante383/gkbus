from ..KWPCommand import KWPCommand

class StartRoutineByLocalId(KWPCommand):
	command = 0x31

	def __init__ (self, data):
		self.data = data