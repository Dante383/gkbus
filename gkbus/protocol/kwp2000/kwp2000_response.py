from dataclasses import dataclass


@dataclass
class Kwp2000ResponseFrame:
	'''
	Kwp2000 response frame. 
	First byte is status - if it's success, status is going to be request service identifier + 0x40
	If it's an error, status is going to be 0x7f, first byte of data is going to be service identifier,
	second byte of data will be error identifier
	'''
	status: int # for success, service identifier + 0x40. error = 0x7f
	data: bytes

	def __repr__ (self) -> str:
		return 'Kwp2000ResponseFrame(status={}, data={!r})'.format(hex(self.status), self.data)

@dataclass
class Kwp2000Response:
	frame: Kwp2000ResponseFrame 

	def success (self) -> bool:
		return self.frame.status != 0x7F

	def get_data (self) -> bytes: # todo: deprecate?
		return self.frame.data