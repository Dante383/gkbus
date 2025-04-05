from enum import Enum


class Kwp2000NegativeStatusIdentifierEnum(Enum):
	GENERAL_REJECT = 0x10
	SERVICE_NOT_SUPPORTED = 0x11
	SUB_FUNCTION_NOT_SUPPORTED_INVALID_FORMAT = 0x12
	INCORRECT_MESSAGE_LENGTH_OR_INVALID_FORMAT = 0x13
	RESPONSE_TOO_LONG = 0x14
	BUSY_REPEAT_REQUEST = 0x21
	CONDITIONS_NOT_CORRECT_OR_REQUEST_SEQUENCE_ERROR = 0x22
	ROUTINE_NOT_COMPLETE = 0x23
	REQUEST_SEQUENCE_ERROR = 0x24
	REQUEST_OUT_OF_RANGE = 0x31
	SECURITY_ACCESS_DENIED_SECURITY_ACCESS_REQUESTED = 0x33
	INVALID_KEY = 0x35
	EXCEED_NUMBER_OF_ATTEMPTS = 0x36
	REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
	DOWNLOAD_NOT_ACCEPTED = 0x40
	IMPROPER_DOWNLOAD_TYPE = 0x41
	CANT_DOWNLOAD_TO_SPECIFIC_ADDRESS = 0x42
	CANT_DOWNLOAD_REQUESTED_NUMBER_OF_BYTES = 0x43
	UPLOAD_NOT_ACCEPTED = 0x50
	IMPROPER_UPLOAD_TYPE = 0x51
	CANT_UPLOAD_FROM_SPECIFIED_ADDRESS = 0x52
	CANT_UPLOAD_REQUESTED_NUMBER_OF_BYTES = 0x53
	UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70
	TRANSFER_SUSPENDED = 0x71
	GENERAL_PROGRAMMING_FAILURE = 0x72
	WRONG_BLOCK_SEQUENCE_COUNTER = 0x73
	ILLEGAL_ADDRESS_IN_BLOCK_TRANSFER = 0x74
	ILLEGAL_BYTE_COUNT_IN_BLOCK_TRANSFER = 0x75
	ILLEGAL_BLOCK_TRANSFER_TYPE = 0x76
	BLOCK_TRANSFER_DATA_CHECKSUM_ERROR = 0x77
	REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING = 0x78
	INCORRECT_BYTE_COUNT_DURING_BLOCK_TRANSFER = 0x79
	SUBFUNCTION_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7E
	SERVICE_NOT_SUPPORTED_IN_CURRENT_SESSION = 0x7F
	SERVICE_NOT_SUPPORTED_IN_ACTIVE_DIAGNOSTIC_SESSION = 0x80
	RPM_TOO_HIGH = 0x81
	RPM_TOO_LOW = 0x82
	ENGINE_IS_RUNNING = 0x83
	ENGINE_IS_NOT_RUNNING = 0x84
	ENGINE_RUN_TIME_TOO_LOW = 0x85
	TEMPERATURE_TOO_HIGH = 0x86
	TEMPERATURE_TOO_LOW = 0x87
	VEHICLE_SPEED_TOO_HIGH = 0x88
	VEHICLE_SPEED_TOO_LOW = 0x89
	THROTTLE_PEDAL_TOO_HIGH = 0x8A
	THROTTLE_PEDAL_TOO_LOW = 0x8B
	TRANSMISSION_RANGE_NOT_IN_NEUTRAL = 0x8C
	TRANSMISSION_RANGE_NOT_IN_GEAR = 0x8D
	BRAKE_SWITCH_ES_NOT_CLOSED_PEDAL_NOT_APPLIED = 0x8F
	SHIFTER_LEVER_NOT_IN_PARK = 0x90
	TORQUE_CONVERTER_CLUTCH_LOCKED = 0x91
	VOLTAGE_TOO_HIGH = 0x92
	VOLTAGE_TOO_LOW = 0x93
	DATA_DECOMPRESSION_FAILED = 0x9A
	DATA_DECRYPTION_FAILED = 0x9B
	ECU_NOT_RESPONDING = 0xA0
	ECU_ADDRESS_UNKNOWN = 0xA1

class Kwp2000NegativeStatusMessageEnum(Enum):
	GENERAL_REJECT = 'General Reject'
	SERVICE_NOT_SUPPORTED = 'Service Not Supported'
	SUB_FUNCTION_NOT_SUPPORTED_INVALID_FORMAT = 'Sub Function Not Supported / Invalid Format'
	INCORRECT_MESSAGE_LENGTH_OR_INVALID_FORMAT = 'Incorrect message length or invalid format'
	RESPONSE_TOO_LONG = 'Response too long'
	BUSY_REPEAT_REQUEST = 'Busy / Repeat Request'
	CONDITIONS_NOT_CORRECT_OR_REQUEST_SEQUENCE_ERROR = 'Conditions Not Correct Or Request Sequence Error'
	ROUTINE_NOT_COMPLETE = 'Routine Not Complete'
	REQUEST_SEQUENCE_ERROR = 'Request sequence error'
	REQUEST_OUT_OF_RANGE = 'Request out of range'
	SECURITY_ACCESS_DENIED_SECURITY_ACCESS_REQUESTED = 'Security Access Denied / Security Access Requested'
	INVALID_KEY = 'Invalid Key'
	EXCEED_NUMBER_OF_ATTEMPTS = 'Exceed number of attempts'
	REQUIRED_TIME_DELAY_NOT_EXPIRED = 'Required time delay not expired'
	DOWNLOAD_NOT_ACCEPTED = 'Download not accepted'
	IMPROPER_DOWNLOAD_TYPE = 'Improper download type'
	CANT_DOWNLOAD_TO_SPECIFIC_ADDRESS = "Can't download to specific address"
	CANT_DOWNLOAD_REQUESTED_NUMBER_OF_BYTES = "Can't download requested number of bytes"
	UPLOAD_NOT_ACCEPTED = 'Upload not accepted'
	IMPROPER_UPLOAD_TYPE = 'Improper upload type'
	CANT_UPLOAD_FROM_SPECIFIED_ADDRESS = "Can't upload from specified address"
	CANT_UPLOAD_REQUESTED_NUMBER_OF_BYTES = "Can't upload requested number of bytes"
	UPLOAD_DOWNLOAD_NOT_ACCEPTED = 'Upload/download not accepted'
	TRANSFER_SUSPENDED = 'Transfer suspended'
	GENERAL_PROGRAMMING_FAILURE = 'General programming failure'
	WRONG_BLOCK_SEQUENCE_COUNTER = 'Wrong block sequence counter'
	ILLEGAL_ADDRESS_IN_BLOCK_TRANSFER = 'Illegal address in block transfer'
	ILLEGAL_BYTE_COUNT_IN_BLOCK_TRANSFER = 'Illegal byte count in block transfer'
	ILLEGAL_BLOCK_TRANSFER_TYPE = 'Illegal block transfer type'
	BLOCK_TRANSFER_DATA_CHECKSUM_ERROR = 'Block transfer data checksum error'
	REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING = 'Request correctly received / Response pending'
	INCORRECT_BYTE_COUNT_DURING_BLOCK_TRANSFER = 'Incorrect byte count during block transfer'
	SUBFUNCTION_NOT_SUPPORTED_IN_ACTIVE_SESSION = 'Subfunction not supported in active session'
	SERVICE_NOT_SUPPORTED_IN_CURRENT_SESSION = 'Service not supported in current session'
	SERVICE_NOT_SUPPORTED_IN_ACTIVE_DIAGNOSTIC_SESSION = 'Service not supported in active diagnostic session'
	RPM_TOO_HIGH = 'RPM too high'
	RPM_TOO_LOW = 'RPM too low'
	ENGINE_IS_RUNNING = 'Engine is running'
	ENGINE_IS_NOT_RUNNING = 'Engine is not running'
	ENGINE_RUN_TIME_TOO_LOW = 'Engine run time too low'
	TEMPERATURE_TOO_HIGH = 'Temperature too high'
	TEMPERATURE_TOO_LOW = 'Temperature too low'
	VEHICLE_SPEED_TOO_HIGH = 'Vehicle speed too high'
	VEHICLE_SPEED_TOO_LOW = 'Vehicle speed too low'
	THROTTLE_PEDAL_TOO_HIGH = 'Throttle/pedal too high'
	THROTTLE_PEDAL_TOO_LOW = 'Throttle/pedal too low'
	TRANSMISSION_RANGE_NOT_IN_NEUTRAL = 'Transmission range not in neutral'
	TRANSMISSION_RANGE_NOT_IN_GEAR = 'Transmission range not in gear'
	BRAKE_SWITCH_ES_NOT_CLOSED_PEDAL_NOT_APPLIED = 'Brake switch(es) not closed (pedal not applied)'
	SHIFTER_LEVER_NOT_IN_PARK = 'Shifter lever not in park'
	TORQUE_CONVERTER_CLUTCH_LOCKED = 'Torque converter clutch locked'
	VOLTAGE_TOO_HIGH = 'Voltage too high'
	VOLTAGE_TOO_LOW = 'Voltage too low'
	DATA_DECOMPRESSION_FAILED = 'Data decompression failed'
	DATA_DECRYPTION_FAILED = 'Data decryption failed'
	ECU_NOT_RESPONDING = 'ECU not responding'
	ECU_ADDRESS_UNKNOWN = 'ECU address unknown'

class Kwp2000NegativeStatus:
	identifier: int = 0x0
	name: str = '' 
	message: str = ''

	def __init__ (self, identifier: int) -> None:
		self.identifier = identifier
		try:
			self.name = Kwp2000NegativeStatusIdentifierEnum(self.identifier).name
		except ValueError:
			return

		try:
			self.message = Kwp2000NegativeStatusMessageEnum[self.name].value
		except KeyError:
			self.message = 'Unknown'

	def get_identifier (self) -> int:
		return self.identifier

	def get_name (self) -> str:
		return self.name

	def get_message (self) -> str:
		return self.message

	def __str__ (self) -> str:
		return 'Kwp2000NegativeStatus(identifier={},message={})'.format(hex(self.identifier), self.message)