from ..KWPCommand import KWPCommand

class StopRoutineByLocalId(KWPCommand):
	command = 0x32

	def __init__ (self, data):
		self.data = data