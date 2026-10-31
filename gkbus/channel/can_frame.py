from dataclasses import dataclass
from typing import Self

STANDARD_ID_MASK = 0x7FF
EXTENDED_ID_MASK = 0x1FFFFFFF


@dataclass(frozen=True)
class CanFrame:
	'''
	A single classic CAN frame

	:param identifier: arbitration id
	:param data: up to 8 bytes
	:param extended: 29 bit identifier. If not given, it's extended when the
		identifier doesn't fit in 11 bits
	'''
	identifier: int
	data: bytes
	extended: bool | None = None

	def __post_init__ (self) -> None:
		object.__setattr__(self, 'data', bytes(self.data))
		if self.extended is None:
			object.__setattr__(self, 'extended', self.identifier > STANDARD_ID_MASK)

@dataclass
class CanFilter:
	'''
	Receive only frames whose identifier matches can_id on the bits set in can_mask
	'''
	can_id: int
	can_mask: int = STANDARD_ID_MASK

	@classmethod
	def for_id (cls, can_id: int) -> Self:
		'''
		Filter matching exactly one identifier, 11 or 29 bit
		'''
		return cls(can_id, EXTENDED_ID_MASK if can_id > STANDARD_ID_MASK else STANDARD_ID_MASK)

	def matches (self, identifier: int) -> bool:
		return identifier & self.can_mask == self.can_id & self.can_mask
