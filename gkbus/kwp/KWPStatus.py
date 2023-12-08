KWP2000_status_def = {
	0x10: 'General Reject',
	0x11: 'Service Not Supported',
	0x12: 'Sub Function Not Supported / Invalid Format',
	0x21: 'Busy / Repeat Request',
	0x22: 'Conditions Not Correct Or Request Sequence Error',
	0x23: 'Routine Not Complete',
	0x31: 'Request out of range',
	0x33: 'Security Access Denied / Security Access Requested',
	0x35: 'Invalid Key',
	0x36: 'Exceed number of attempts',
	0x37: 'Required time delay not expired',
	0x40: 'Download not accepted',
	0x50: 'Upload not accepted',
	0x71: 'Transfer suspended',
	0x78: 'Request correctly received / Response pending',
	0x80: 'Service not supported in active diagnostic session',

	# 0x81 - 0x8F reserved for future use by iso 14230
	# 0x90 - 0x99 - to be defined by DCX diagnostics 

	0x9A: 'Data decompression failed',
	0x9B: 'Data decryption failed',

	# 0x9C - 0x99 - to be defined by DCX diagnostics 

	0xA0: 'ECU not responding',
	0xA1: 'ECU address unknown'

	# 0xA2 - 0xF9 - To be defined by DCX diagnostics
	# 0xFF - reserved for future use by iso 14230
}

class KWPStatus:
	code = 0x0 
	name = ''

	def __init__ (self, code):
		self.code = code
		try:
			self.name = KWP2000_status_def[code]
		except KeyError:
			self.name = 'Unknown' # todo: raise exception?

	def get_code (self) -> int:
		return self.code

	def get_name (self) -> str:
		return self.name

	def __str__ (self) -> str:
		return '<{} - {}>'.format(self.code, self.name)