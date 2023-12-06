from ..KWPCommand import KWPCommand

class ControlDTCSetting(KWPCommand):
	command = 0x85

	def __init__ (self, data):
		self.data = data