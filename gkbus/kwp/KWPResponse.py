class KWPResponse:
	data: list[int] = False

	def set_data (self, data: list[int]):
		self.data = data
		return self

	def get_data (self) -> list[int]:
		return self.data

	def __str__ (self) -> str:
		return '<KWPResponse: {}>'.format(' '.join([hex(x) for x in self.get_data()]))