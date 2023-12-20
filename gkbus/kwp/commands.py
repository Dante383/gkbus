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

class DynamicallyDefineLocalIdentifier(KWPCommand):
	command = 0x2C

class ECUReset(KWPCommand):
	command = 0x11

class EnableNormalMessageTransmission(KWPCommand):
	command = 0x29

class InputOutputControlByLocalIdentifier(KWPCommand):
	command = 0x30

class ReadDataByIdentifier(KWPCommand):
	command = 0x22

class ReadDataByLocalIdentifier(KWPCommand):
	command = 0x21

class ReadDTCsByStatus(KWPCommand):
	command = 0x18

class ReadEcuIdentification(KWPCommand):
	command = 0x1A

	def __init__ (self, identifier):
		self.set_data([identifier])

class ReadMemoryByAddress(KWPCommand):
	command = 0x23

	def __init__ (self, offset=0x000000, size=0xFE):
		byte1 = (offset >> 16) & 0xFF
		byte2 = (offset >> 8) & 0xFF
		byte3 = offset & 0xFF

		self.set_data([byte1, byte2, byte3, size])

class ReadStatusOfDTC(KWPCommand):
	command = 0x01

	def __init__ (self, dtc):
		self.set_data([dtc])

class RequestDownload(KWPCommand):
	command = 0x34

	def __init__ (self, offset, size):
		offset_b1 = (offset >> 16) & 0xFF
		offset_b2 = (offset >> 8) & 0xFF
		offset_b3 = offset & 0xFF

		data_format = 0x00 # uncompressed, unencrypted

		size_b1 = (size >> 16) & 0xFF
		size_b2 = (size >> 8) & 0xFF
		size_b3 = size & 0xFF

		self.set_data([offset_b1, offset_b2, offset_b3, data_format, size_b1, size_b2, size_b3])

class RequestRoutineResultsByLocalIdentifier(KWPCommand):
	command = 0x33

class RequestTransferExit(KWPCommand):
	command = 0x37

class RequestUpload(KWPCommand):
	command = 0x35

class ResponseOnEvent(KWPCommand):
	command = 0x86

class SecurityAccess(KWPCommand):
	command = 0x27

class StartCommunication(KWPCommand):
	command = 0x81

class StartDiagnosticSession(KWPCommand):
	command = 0x10

class StartRoutineByLocalIdentifier(KWPCommand):
	command = 0x31

class StopCommunication(KWPCommand):
	command = 0x82

class StartDiagnosticSession(KWPCommand):
	command = 0x10

	def __init__ (self, session_type: DiagnosticSession):
		self.set_data([session_type.value])

class StopRoutineByLocalIdentifier(KWPCommand):
	command = 0x32

class TesterPresent(KWPCommand):
	command = 0x3E

class TransferData(KWPCommand):
	command = 0x36

class WriteDataByIdentifier(KWPCommand):
	command = 0x2E

class WriteDataByLocalIdentifier(KWPCommand):
	command = 0x3B

class WriteMemoryByAddress(KWPCommand):
	command = 0x3D

	def __init__ (self, offset, data_to_write):
		size = len(data_to_write)

		byte1 = (offset >> 16) & 0xFF
		byte2 = (offset >> 8) & 0xFF
		byte3 = offset & 0xFF

		self.set_data([byte1, byte2, byte3, size] + data_to_write)

class StopCommunication(KWPCommand):
	command = 0x82

class StopDiagnosticSession(KWPCommand):
	command = 0x20

