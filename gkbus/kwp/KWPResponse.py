class KWPResponse:
	data: list[int] = False

	def set_data (self, data: list[int]):
		self.data = data
		return self

	def get_data (self) -> list[int]:
		return self.data