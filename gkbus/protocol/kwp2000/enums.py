from enum import Enum


class TimingParameterIdentifier(Enum):
	READ_LIMITS_OF_POSSIBLE_TIMING_PARAMETERS = 0x00
	SET_TIMING_PARAMETERS_TO_DEFAULT_VALUES = 0x01
	READ_CURRENTLY_ACTIVE_TIMING_PARAMETERS = 0x02
	SET_TIMING_PARAMETERS_TO_GIVEN_VALUES = 0x03

class DiagnosticSession(Enum):
	DEFAULT = 0x81
	FLASH_REPROGRAMMING = 0x85
	ENGINEERING = 0x86
	ADJUSTMENT = 0x87
	STANDBY = 0x89
	PASSIVE = 0x90
	EXTENDED_DIAGNOSTIC = 0x92

class AccessType(Enum):
	PROGRAMMING_REQUEST_SEED = 0x01
	PROGRAMMING_SEND_KEY = 0x02

class ResetMode(Enum):
	POWER_ON_RESET = 0x01
	NONVOLATILE_MEMORY_RESET = 0x82

class InputOutputControlParameter(Enum):
	RETURN_CONTROL_TO_ECU = 0x00
	REPORT_CURRENT_STATE = 0x01
	RESET_TO_DEFAULT = 0x04
	FREEZE_CURRENT_STATE = 0x05
	SHORT_TERM_ADJUSTMENT = 0x07
	LONG_TERM_ADJUSTMENT = 0x08

class CompressionType(Enum):
	UNCOMPRESSED = 0x0

class EncryptionType(Enum):
	UNENCRYPTED = 0x0

class ResponseType(Enum):
	REQUIRED = 0x01
	NOT_REQUIRED = 0x02