from enum import Enum


class DisconnectType(Enum):
	TEMPORARY = 0x00 
	END_OF_SESSION = 0x01

class DataTransmissionRequest(Enum):
	STOP = 0x00
	START = 0x01

class DataTransmissionMode(Enum):
	START = 0x00
	STOP = 0x01
	PREPARE = 0x02