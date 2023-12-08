from .KWPCommand import KWPCommand

class AccessTimingParameters(KWPCommand):
	command = 0x83

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
	identifier = 0x0

	def __init__ (self, identifier):
		self.identifier = identifier
		self.data = [self.identifier]

class ReadMemoryByAddress(KWPCommand):
	command = 0x23
	offset = 0x000000
	size = 0xFE

	def __init__ (self, offset=0x000000, size=0xFE):
		self.offset = offset
		self.size = size
		byte1 = (self.offset >> 16) & 0xFF
		byte2 = (self.offset >> 8) & 0xFF
		byte3 = self.offset & 0xFF

		self.data = [byte1, byte2, byte3, self.size]

class ReadStatusOfDTC(KWPCommand):
	command = 0x01
	dtc = 0x0

	def __init__ (self, dtc):
		self.dtc = dtc
		self.data = [self.dtc]

class RequestDownload(KWPCommand):
	command = 0x34
	offset = 0x0
	size = 0

	def __init__ (self, offset, size):
		self.offset = offset 
		self.size = size 

		offset_b1 = (self.offset >> 16) & 0xFF
		offset_b2 = (self.offset >> 8) & 0xFF
		offset_b3 = self.offset & 0xFF

		data_format = 0x00 # uncompressed, unencrypted

		size_b1 = (self.size >> 16) & 0xFF
		size_b2 = (self.size >> 8) & 0xFF
		size_b3 = self.size & 0xFF

		self.data = [offset_b1, offset_b2, offset_b3, data_format, size_b1, size_b2, size_b3]

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

class StartRoutineByLocalId(KWPCommand):
	command = 0x31

class StopCommunication(KWPCommand):
	command = 0x82

class StartDiagnosticSession(KWPCommand):
	command = 0x10

	def __init__ (self):
		self.data = [0x85]

class StopRoutineByLocalId(KWPCommand):
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
	offset = 0x0
	size = 0
	data_to_write = []

	def __init__ (self, offset, data_to_write):
		self.offset = offset
		self.data_to_write = data_to_write
		self.size = len(self.data_to_write)

		byte1 = (self.offset >> 16) & 0xFF
		byte2 = (self.offset >> 8) & 0xFF
		byte3 = self.offset & 0xFF

		self.data = [byte1, byte2, byte3, self.size] + self.data_to_write

class StopCommunication(KWPCommand):
	command = 0x82

class StopDiagnosticSession(KWPCommand):
	command = 0x20

