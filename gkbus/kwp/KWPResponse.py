from .KWPStatus import KWPStatus

class KWPResponse:
	status: KWPStatus = False
	data: list[int] = False

	def set_status (self, status: KWPStatus):
		self.status = status
		return self 

	def set_data (self, data: list[int]):
		self.data = data
		return self

	def get_status (self) -> KWPStatus:
		return self.status

	def get_data (self) -> list[int]:
		return self.data