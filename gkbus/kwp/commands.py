import struct
from .KWPCommand import KWPCommand, KWPCommandWithSubservices
from .enums import *

class AccessTimingParameters(KWPCommandWithSubservices): # TimingParameterIdentifier
	command = 0x83
	subservices = {
		TimingParameterIdentifier.READ_LIMITS_OF_POSSIBLE_TIMING_PARAMETERS: 'read_limits_of_possible_timing_parameters',
		TimingParameterIdentifier.SET_TIMING_PARAMETERS_TO_DEFAULT_VALUES: 'set_timing_parameters_to_default_values',
		TimingParameterIdentifier.READ_CURRENTLY_ACTIVE_TIMING_PARAMETERS: 'read_currently_active_timing_parameters',
		TimingParameterIdentifier.SET_TIMING_PARAMETERS_TO_GIVEN_VALUES: 'set_timing_parameters_to_given_values'
	}

	def read_limits_of_possible_timing_parameters (self):
		pass

	def set_timing_parameters_to_default_values (self):
		pass

	def read_currently_active_timing_parameters (self):
		pass

	def set_timing_parameters_to_given_values (self,
			p2min: int,
			p2max: int,
			p3min: int,
			p3max: int,
			p4min: int
		):
		self.set_data([p2min, p2max, p3min, p3max, p4min])

class ClearDiagnosticInformation(KWPCommand):
	command = 0x14

class ControlDTCSetting(KWPCommand):
	command = 0x85

class DisableNormalMessageTransmission(KWPCommand):
	command = 0x28

	def __init__(self, response_type: ResponseType):
		self.set_data([response_type.value])

class DynamicallyDefineLocalIdentifier(KWPCommand):
	command = 0x2C

class ECUReset(KWPCommand):
	command = 0x11

	def __init__ (self, reset_mode: ResetMode):
		self.set_data([reset_mode.value])

class EnableNormalMessageTransmission(KWPCommand):
	command = 0x29

	def __init__ (self, response_type: ResponseType):
		self.set_data([response_type.value])

class InputOutputControlByLocalIdentifier(KWPCommand):
	command = 0x30

	def __init__ (self, control_identifier: int, control_parameter: InputOutputControlParameter, *control_state):
		self.set_data([control_identifier, control_parameter.value, *control_state])

class ReadDataByIdentifier(KWPCommand):
	command = 0x22

class ReadDataByLocalIdentifier(KWPCommand):
	command = 0x21

	def __init__ (self, record_local_identifier: int):
		self.set_data([record_local_identifier])

class ReadDTCsByStatus(KWPCommand):
	command = 0x18

class ReadEcuIdentification(KWPCommand):
	command = 0x1A

	def __init__ (self, identifier):
		self.set_data([identifier])

class ReadMemoryByAddress(KWPCommand):
	command = 0x23

	def __init__ (self, offset: int = 0x000000, size: int = 0xFE):
		address = struct.pack('>L', offset)[1:]

		self.set_data([*address, size])

class ReadStatusOfDTC(KWPCommand):
	command = 0x01

	def __init__ (self, dtc):
		self.set_data([dtc])

class RequestDownload(KWPCommand):
	command = 0x34

	def __init__ (self, 
			offset: int, 
			compression_type: CompressionType,
			encryption_type: EncryptionType,
			size: int
		):
		address = struct.pack('>L', offset)[1:]
		data_format = (compression_type.value << 4) | encryption_type.value
		size = struct.pack('>L', size)[1:]

		self.set_data([*address, data_format, *size])

class RequestRoutineResultsByLocalIdentifier(KWPCommand):
	command = 0x33

	def __init__ (self, routine_identifier: int):
		self.set_data([routine_identifier])

class RequestTransferExit(KWPCommand):
	command = 0x37

class RequestUpload(KWPCommand):
	command = 0x35

	def __init__ (self, 
			offset: int, 
			compression_type: CompressionType,
			encryption_type: EncryptionType,
			size: int
		):
		address = struct.pack('>L', offset)[1:]
		data_format = (compression_type.value << 4) | encryption_type.value
		size = struct.pack('>L', size)[1:]

		self.set_data([*address, data_format, *size])

class ResponseOnEvent(KWPCommand):
	command = 0x86

class SecurityAccess(KWPCommandWithSubservices):
	command = 0x27

	subservices = {
		AccessType.PROGRAMMING_REQUEST_SEED: 'request_seed',
		AccessType.PROGRAMMING_SEND_KEY: 'send_key'
	}

	def request_seed (self):
		pass

	def send_key (self, key: int):
		key = key.to_bytes((key.bit_length()//6), 'big')
		self.set_data([*key])

class StartCommunication(KWPCommand):
	command = 0x81

class StartRoutineByLocalIdentifier(KWPCommand):
	command = 0x31

	def __init__ (self, routine_identifier: int, *routine_entry_option):
		self.set_data([routine_identifier, *routine_entry_option])

class StartDiagnosticSession(KWPCommand):
	command = 0x10

	def __init__ (self, session_type: DiagnosticSession, dev_baudrate_identifier: int = None):
		self.set_data([session_type.value])
		# while it's not present in any official documentations, most ECU manufacturers use 
		# the second parameter of StartDiagnosticSession as a baudrate switch. 
		# for example, 0x03 on SIMK43 will result in 40k baud, 0x04 - 60k 
		if (dev_baudrate_identifier): 
			self.set_data(self.get_data() + [dev_baudrate_identifier])

class StopCommunication(KWPCommand):
	command = 0x82

class StopRoutineByLocalIdentifier(KWPCommand):
	command = 0x32

	def __init__ (self, routine_identifier: int, *routine_exit_option):
		self.set_data([routine_identifier, *routine_exit_option])

class TesterPresent(KWPCommand):
	command = 0x3E

	def __init__ (self, response_type: ResponseType):
		self.set_data([response_type.value])

class TransferData(KWPCommand):
	command = 0x36

class WriteDataByIdentifier(KWPCommand):
	command = 0x2E

class WriteDataByLocalIdentifier(KWPCommand):
	command = 0x3B

	def __init__ (self, record_local_identifier: int, record_value: list[int]):
		self.set_data([record_local_identifier] + record_value)

class WriteMemoryByAddress(KWPCommand):
	command = 0x3D

	def __init__ (self, offset: int, data_to_write: list[int]):
		size = len(data_to_write)

		address = struct.pack('>L', offset)[1:]

		self.set_data([*address, size] + data_to_write)

class StopCommunication(KWPCommand):
	command = 0x82

class StopDiagnosticSession(KWPCommand):
	command = 0x20

