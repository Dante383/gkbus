import struct

from typing_extensions import Self

from .enums import *
from .kwp2000_command import Kwp2000Command, Kwp2000CommandWithSubservices


class AccessTimingParameters(Kwp2000CommandWithSubservices): # TimingParameterIdentifier
	service_identifier = 0x83

	def read_limits_of_possible_timing_parameters (self) -> Self:
		return self.set_subservice_identifier(TimingParameterIdentifier.READ_LIMITS_OF_POSSIBLE_TIMING_PARAMETERS.value)

	def set_timing_parameters_to_default_values (self) -> Self:
		return self.set_subservice_identifier(TimingParameterIdentifier.SET_TIMING_PARAMETERS_TO_DEFAULT_VALUES.value)

	def read_currently_active_timing_parameters (self) -> Self:
		return self.set_subservice_identifier(TimingParameterIdentifier.SET_TIMING_PARAMETERS_TO_GIVEN_VALUES.value)

	def set_timing_parameters_to_given_values (self,
			p2min: int,
			p2max: int,
			p3min: int,
			p3max: int,
			p4min: int
		) -> Self:
		self.set_subservice_identifier(TimingParameterIdentifier.SET_TIMING_PARAMETERS_TO_GIVEN_VALUES.value)
		return self.append_data(bytes([p2min, p2max, p3min, p3max, p4min]))

class ClearDiagnosticInformation(Kwp2000Command):
	service_identifier = 0x14

class ControlDTCSetting(Kwp2000Command):
	service_identifier = 0x85

class DisableNormalMessageTransmission(Kwp2000Command):
	service_identifier = 0x28

	def init(self, response_type: ResponseType) -> None:
		self.set_data(bytes([response_type.value]))

class DynamicallyDefineLocalIdentifier(Kwp2000Command):
	service_identifier = 0x2C

class ECUReset(Kwp2000Command):
	'''
	This service requests the ECU to effectively perform a reset 
	based on the content of the reset_mode parameter. 
	The reset_mode parameter may specify a reset for the entire ECU 
	or selective portions of on-board memory
	'''
	service_identifier = 0x11

	def init (self, reset_mode: ResetMode) -> None:
		self.set_data(bytes([reset_mode.value]))

class EnableNormalMessageTransmission(Kwp2000Command):
	service_identifier = 0x29

	def init (self, response_type: ResponseType) -> None:
		self.set_data(bytes([response_type.value]))

class InputOutputControlByLocalIdentifier(Kwp2000Command):
	service_identifier = 0x30

	def init (self, control_identifier: int, control_parameter: InputOutputControlParameter, *control_state) -> None:
		self.set_data(bytes([control_identifier, control_parameter.value, *control_state]))

class ReadDataByIdentifier(Kwp2000Command):
	service_identifier = 0x22

class ReadDataByLocalIdentifier(Kwp2000Command):
	service_identifier = 0x21

	def init (self, record_local_identifier: int) -> None:
		self.set_data(bytes([record_local_identifier]))

class ReadDTCsByStatus(Kwp2000Command):
	service_identifier = 0x18

class ReadEcuIdentification(Kwp2000Command):
	service_identifier = 0x1A

	def init (self, identifier) -> None:
		self.set_data(bytes([identifier]))

class ReadMemoryByAddress(Kwp2000Command):
	service_identifier = 0x23

	def init (self, offset: int = 0x000000, size: int = 0xFE) -> None:
		address = struct.pack('>L', offset)[1:]

		self.set_data(bytes([*address, size]))

class ReadStatusOfDTC(Kwp2000Command):
	service_identifier = 0x01

	def init (self, dtc) -> None:
		self.set_data(bytes([dtc]))

class RequestDownload(Kwp2000Command):
	service_identifier = 0x34

	def init (self, 
			offset: int, 
			compression_type: CompressionType,
			encryption_type: EncryptionType,
			size: int
		) -> None:
		address = struct.pack('>L', offset)[1:]
		data_format = (compression_type.value << 4) | encryption_type.value
		size = struct.pack('>L', size)[1:]

		self.set_data(bytes([*address, data_format, *size]))

class RequestRoutineResultsByLocalIdentifier(Kwp2000Command):
	service_identifier = 0x33

	def init (self, routine_identifier: int) -> None:
		self.set_data(bytes([routine_identifier]))

class RequestTransferExit(Kwp2000Command):
	service_identifier = 0x37

class RequestUpload(Kwp2000Command):
	service_identifier = 0x35

	def init (self, 
			offset: int, 
			compression_type: CompressionType,
			encryption_type: EncryptionType,
			size: int
		) -> None:
		address = struct.pack('>L', offset)[1:]
		data_format = (compression_type.value << 4) | encryption_type.value
		size = struct.pack('>L', size)[1:]

		self.set_data(bytes([*address, data_format, *size]))

class ResponseOnEvent(Kwp2000Command):
	service_identifier = 0x86

class SecurityAccess(Kwp2000CommandWithSubservices): # @todo: refactor
	service_identifier = 0x27

	def request_seed (self) -> Self:
		return self.set_subservice_identifier(AccessType.PROGRAMMING_REQUEST_SEED.value)

	def send_key (self, key: int) -> Self:
		self.set_subservice_identifier(AccessType.PROGRAMMING_SEND_KEY.value)
		key = key.to_bytes(2, 'big')
		#key = key.to_bytes((key.bit_length()//6), 'big')
		return self.append_data(bytes([*key]))

class StartCommunication(Kwp2000Command):
	service_identifier = 0x81

class StartRoutineByLocalIdentifier(Kwp2000Command):
	service_identifier = 0x31

	def init (self, routine_identifier: int, *routine_entry_option) -> None:
		self.set_data(bytes([routine_identifier, *routine_entry_option]))

class StartDiagnosticSession(Kwp2000Command):
	'''
	Start diagnostic session on the ECU. 

	- By default, Normal/Default session (0x81) is automatically enabled by the ECU,
	but not if the ECU entered the Passive Session (0x90) before powering down.
	- ECU will return to Normal/Default session (0x81) after timeout 
	of another diagnostic session 
	- A positive response will be returned if the requested session was already active
	- ECU will stay in it's previous session if the requested session is 
	unable to be activated
	- Sessions Flash Reprogramming (0x85), Stand By (0x89), Extended Diagnostic (0x92)
	must be kept active with TesterPresent (0x3E) service if no other diagnostic 
	messages are sent within P3 max (see timing parameters)
	'''

	service_identifier = 0x10

	def init (self, session_type: DiagnosticSession, dev_baudrate_identifier: int | None = None) -> None:
		self.set_data(bytes([session_type.value]))
		# while it's not present in any official documentations, most ECU manufacturers use 
		# the second parameter of StartDiagnosticSession as a baudrate switch. 
		# for example, 0x03 on SIMK43 will result in 40k baud, 0x04 - 60k 
		if (dev_baudrate_identifier): 
			self.append_data(bytes([dev_baudrate_identifier]))

class StopCommunication(Kwp2000Command):
	service_identifier = 0x82

class StopRoutineByLocalIdentifier(Kwp2000Command):
	service_identifier = 0x32

	def init (self, routine_identifier: int, *routine_exit_option) -> None:
		self.set_data(bytes([routine_identifier, *routine_exit_option]))

class TesterPresent(Kwp2000Command):
	service_identifier = 0x3E

	def init (self, response_type: ResponseType) -> None:
		self.set_data(bytes([response_type.value]))

class TransferData(Kwp2000Command):
	service_identifier = 0x36

class WriteDataByIdentifier(Kwp2000Command):
	service_identifier = 0x2E

class WriteDataByLocalIdentifier(Kwp2000Command):
	service_identifier = 0x3B

	def init (self, record_local_identifier: int, record_value: list[int]) -> None:
		self.set_data(bytes([record_local_identifier] + record_value))

class WriteMemoryByAddress(Kwp2000Command):
	service_identifier = 0x3D

	def init (self, offset: int, data_to_write: list[int]) -> None:
		size = len(data_to_write)

		address = struct.pack('>L', offset)[1:]

		self.set_data(bytes([*address, size] + data_to_write))

class StopDiagnosticSession(Kwp2000Command):
	service_identifier = 0x20