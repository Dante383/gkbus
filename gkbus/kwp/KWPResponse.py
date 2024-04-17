from typing import List

class KWPResponse:
	data: List[int] = False

	def set_data (self, data: List[int]):
		self.data = data
		return self

	def get_data (self) -> List[int]:
		return self.data

	def __str__ (self) -> str:
		return '<KWPResponse: {}>'.format(' '.join([hex(x) for x in self.get_data()]))