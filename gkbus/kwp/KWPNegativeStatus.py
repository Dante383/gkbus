KWP2000_negative_status_def = {
	0x10: 'General Reject',
	0x11: 'Service Not Supported',
	0x12: 'Sub Function Not Supported / Invalid Format',
	0x13: 'Incorrect message length or invalid format',
	0x14: 'Response too long',
	0x21: 'Busy / Repeat Request',
	0x22: 'Conditions Not Correct Or Request Sequence Error',
	0x23: 'Routine Not Complete',
	0x24: 'Request sequence error',
	0x31: 'Request out of range',
	0x33: 'Security Access Denied / Security Access Requested',
	0x35: 'Invalid Key',
	0x36: 'Exceed number of attempts',
	0x37: 'Required time delay not expired',
	0x40: 'Download not accepted',
	0x41: 'Improper download type',
	0x42: 'Can\'t download to specific address',
	0x43: 'Can\'t download requested number of bytes',
	0x50: 'Upload not accepted',
	0x51: 'Improper upload type',
	0x52: 'Can\'t upload from specified address',
	0x53: 'Can\'t upload requested number of bytes',
	0x70: 'Upload/download not accepted',
	0x71: 'Transfer suspended',
	0x72: 'General programming failure',
	0x73: 'Wrong block sequence counter',
	0x74: 'Illegal address in block transfer',
	0x75: 'Illegal byte count in block transfer',
	0x76: 'Illegal block transfer type',
	0x77: 'Block transfer data checksum error',
	0x78: 'Request correctly received / Response pending',
	0x79: 'Incorrect byte count during block transfer',
	0x7E: 'Subfunction not supported in active session',
	0x7F: 'Service not supported in current session',
	0x80: 'Service not supported in active diagnostic session',
	0x81: 'RPM too high',
	0x82: 'RPM too low',
	0x83: 'Engine is running',
	0x84: 'Engine is not running',
	0x85: 'Engine run time too low',
	0x86: 'Temperature too high',
	0x87: 'Temperature too low',
	0x88: 'Vehicle speed too high',
	0x89: 'Vehicle speed too low',
	0x8A: 'Throttle/pedal too high',
	0x8B: 'Throttle/pedal too low',
	0x8C: 'Transmission range not in neutral',
	0x8D: 'Transmission range not in gear',
	0x8F: 'Brake switch(es) not closed (pedal not applied)',
	
	0x90: 'Shifter lever not in park',
	0x91: 'Torque converter clutch locked',
	0x92: 'Voltage too high',
	0x93: 'Voltage too low',

	0x9A: 'Data decompression failed',
	0x9B: 'Data decryption failed',

	# 0x9C - 0x99 - to be defined by DCX diagnostics 

	0xA0: 'ECU not responding',
	0xA1: 'ECU address unknown'

	# 0xA2 - 0xF9 - To be defined by DCX diagnostics
	# 0xFF - reserved for future use by iso 14230
}

class KWPNegativeStatus:
	code = 0x0 
	name = ''

	def __init__ (self, code):
		self.code = code
		try:
			self.name = KWP2000_negative_status_def[code]
		except KeyError:
			self.name = 'Unknown' # todo: raise exception?

	def get_code (self) -> int:
		return self.code

	def get_name (self) -> str:
		return self.name

	def __str__ (self) -> str:
		return '<{} - {}>'.format(hex(self.code), self.name)