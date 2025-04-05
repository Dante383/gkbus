from ctypes import LittleEndianStructure


class LittleEndianBitfield(LittleEndianStructure):
	_pack_ = 1

	def _to_dict (self) -> dict:
		return dict((field, getattr(self, field)) for field, _, _ in self._fields_ if getattr(self, field) != 0)

	def __str__ (self) -> str:
		return '{}({})'.format(
			type(self).__name__,
			', '.join([f'{k}={v}' for k,v in self._to_dict().items()])
		)