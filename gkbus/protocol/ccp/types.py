from ctypes import c_uint8

from ...utils import LittleEndianBitfield


class ResourceMaskBitfield(LittleEndianBitfield):
	_fields_ = [ # res - reserved
		('CAL', c_uint8, 1),
		('DAQ', c_uint8, 1),
		('res', c_uint8, 1),
		('res1', c_uint8, 1),
		('res2', c_uint8, 1),
		('res3', c_uint8, 1),
		('PGM', c_uint8, 1),
		('res4', c_uint8, 1)
	]

class SessionStatusBitfield(LittleEndianBitfield):
	_fields_ = [ # res - reserved
		('CAL', c_uint8, 1),
		('DAQ', c_uint8, 1),
		('RESUME', c_uint8, 1),
		('res', c_uint8, 1),
		('res1', c_uint8, 1),
		('res2', c_uint8, 1),
		('STORE', c_uint8, 1),
		('RUN', c_uint8, 1),
	]