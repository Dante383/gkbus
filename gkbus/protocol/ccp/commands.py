from typing import Union

from .ccp_command import CcpCommand
from .enums import DataTransmissionMode, DataTransmissionRequest, DisconnectType
from .types import ResourceMaskBitfield, SessionStatusBitfield


class Connect(CcpCommand):
	'''
	Estabilish a master-slave connection
	
	:param station_address: station address, word. MSB
	'''
	code = 0x01

	def init (self, station_address: int) -> None:
		self.data = station_address.to_bytes(2, 'little')

class ExchangeStationIdentifications(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	The CCP master and slave stations exchange IDs for automatic session
	configuration. This might include automatic assignment of a data acquisition
	setup file depending on the slave's returned ID (Plug´n´Play). 
	The slave device automatically sets the Memory Transfer Address 0 (MTA0) to
	the location from which the CCP master may subsequently upload the requested
	ID using UPLOAD. See also the SET_MTA and UPLOAD command
	description.
	'''
	code = 0x17

class GetSeedForKey(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	See EXCHANGE_ID for a description of the resource mask.
	Only one resource or function may be requested with one GET_SEED
	command If more than one resource is requested, the GET_SEED command
	together with the following UNLOCK command has to be performed multiple
	times.
	Returns ´seed´ data for a seed&key algorithm for computing the ´key´ to
	unlock the requested function for authorized access (see 'Unlock Protection'
	below).

	:param resource_mask: Requested slave resource or function
	'''
	code = 0x12

	def init (self, resource_mask: Union[int, ResourceMaskBitfield]) -> None:
		if isinstance(resource_mask, ResourceMaskBitfield):
			self.data = bytes(resource_mask)
		else:
			self.data = resource_mask.to_bytes(1, 'little')
		
class UnlockProtection(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	Unlocks the slave devices security protection (if applicable) using a ´key´ computed from
	´seed´. See seed&key above

	:param key: key calculated from the seed. Up to 6 bytes
	'''
	code = 0x13

	def init (self, key: bytes) -> None:
		self.data = key

class SetMemoryTransferAddress(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
		
	This command will initialize a base pointer (32Bit + extension) for all following memory
	transfers. The address extension depends on the slave controller's organization and may
	identify a switchable memory bank or a memory segment.
	The MTA number (handle) is used to identify different transfer address locations (pointers).
	MTA0 is used by the commands DNLOAD, UPLOAD, DNLOAD_6 , SELECT_CAL_PAGE,
	CLEAR_MEMORY, PROGRAM and PROGRAM_6. MTA1 is used by the MOVE command.
	See also command ‘MOVE’.

	:param mta_number: 0 or 1. 
		Used to identify pointer locations; 
		0 for download, upload, select_cal_page, clear_memory, program
		1 for move
	:param address_extension: 1 byte address extension
	:param address: unsigned long address
	'''
	code = 0x02

	def init (self, mta_number: int, address_extension: int, address: int) -> None:
		if mta_number not in [0, 1]:
			raise ValueError(f'Invalid MTA number: {mta_number}. Valid values are either 0 or 1')

		self.data = bytes([mta_number, address_extension]) + address.to_bytes(4, 'little')

class DataDownload(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	The data block of the specified length (size) contained in the CRO will be copied into
	memory, starting at the current Memory Transfer Address 0 (MTA0). The MTA0 pointer will
	be post-incremented by the value of 'size'.

	:param size: size of the data block about to be transfered (max 5 bytes)
	:param data: data to be transferred
	'''
	code = 0x03

	def init (self, size: int, data: bytes) -> None:
		if (size > 5):
			raise ValueError(f'Invalid size: {size}. Max value is 5')

		if (len(data) > 5):
			raise ValueError('Invalid data size. Max length is 5')

		self.data = size.to_bytes(1, 'little') + data

class DataDownload6Bytes(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	The data block with the fixed length (size) of 6 bytes contained in the CRO will be copied
	into memory, starting at the current Memory Transfer Address 0 (MTA0). The MTA0 pointer
	will be post-incremented by the value 6.

	:param data: 6 bytes of data to be transferred
	'''
	code = 0x23

	def init (self, data: bytes) -> None:
		if (len(data) > 6):
			raise ValueError('Invalid data size. Max length is 6')

		self.data = data

class DataUpload(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	A data block of the specified length (size), starting at current MTA0, will be copied into the
	corresponding DTO data field. The MTA0 pointer will be post-incremented by the value of
	'size'.

	:param size: size of data block to be uploaded - maximum 5
	'''
	code = 0x04

	def init (self, size: int) -> None:
		if (size > 5):
			raise ValueError(f'Invalid requested size: {size}. Maximum value is 5')

		self.data = size.to_bytes(1, 'little')

class ShortUpload(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	A data block of the specified length (size), starting at source address will be copied into the
	corresponding DTO data field. The MTA0 pointer remains unchanged.
	
	:param size: size of data block to be uploaded - maximum 5
	:param address_extension: byte address extension
	:param address: address - unsigned long
	'''
	code = 0x0F

	def init (self, size: int, address_extension: int, address: int) -> None:
		if (size > 5):
			raise ValueError(f'Invalid requested size: {size}. Maximum value is 5')

		self.data = bytes([size, address_extension]) + address.to_bytes(4, 'little')

class SelectCalibrationPage(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	This command's function depends on the ECU implementation. The previously initialized
	MTA0 points to the start of the calibration data page that is selected as the currently active
	page by this command.
	'''
	code = 0x11

class GetSizeOfDaqList(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	Returns the size of the specified DAQ list as the number of available Object
	DescriptorTables (ODTs) and clears the current list. If the specified list number is not
	available, size = 0 should be returned. The DAQ list is initialized and data acquisition by this
	list is stopped.
	An individual CAN Identifier may be assigned to a DAQ list to configure multi ECU data
	acquisition. This feature is optional. If the given identifier isn’t possible, an error code is
	returned. 29 bit CAN identifiers are marked by the most significant bit set.

	:param list_number: DAQ list number (0, 1, ...)
	:param can_identifier: CAN identifier of DTO dedicated to list number. unsigned long
	'''
	code = 0x14

	def init (self, list_number: int, can_identifier: int = 0) -> None:
		self.data = list_number.to_bytes(1, 'little') + b'\xFF' + can_identifier.to_bytes(4, 'little')

class SetDaqListPointer(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	Initializes the DAQ list pointer for a subsequent write to a DAQ list.
	See also 'Organization of Data Acquisition Messages'.

	:param list_number: DAQ list number (0, 1, ...)
	:param odt_number: Object Descriptor Table ODT number (0, 1, ...)
	:param element_number: Element number within ODT (0, 1, ...)
	'''
	code = 0x15

	def init (self, list_number: int, odt_number: int, element_number: int) -> None:
		self.data = bytes([list_number, odt_number, element_number])

class WriteDaqListEntry(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	Writes one entry (description of single DAQ element) to a DAQ list defined by the DAQ list
	pointer (see SET_DAQ_PTR). The following DAQ element sizes are defined: 1 byte , 2
	bytes (type word), 4 bytes (type long / Float).
	An ECU may not support individual address extensions for each element and 2 or 4 byte
	element sizes. It is the responsibility of the master device to care for the ECU limitations.
	The limitations may be defined in the slave device description file (e.g. ASAP2).
	It is the responsibility of the slave device, that all bytes of a DAQ element are consistent
	upon transmission.
	See also 'Organization of Data Acquisition Messages'.

	:param size: Size of DAQ element in bytes (1, 2, 4)
	:param address_extension: Address extension of DAQ element
	:param address: Address of DAQ element - unsigned long
	'''
	code = 0x16

	def init (self, size: int, address_extension: int, address: int) -> None:
		self.data = bytes([size, address_extension]) + address.to_bytes(4, 'little')

class StartStopDataTransmission(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	This command is used to start or to stop the data acquisition or to prepare a synchronized
	start of the specified DAQ list. The Last ODT number specifies which ODTs (From 0 to
	Last ODT number) of this DAQ list should be transmitted. The Event Channel No.
	specifies the generic signal source that effectively determines the data transmission timing.
	To allow reduction of the desired transmission rate, a prescaler may be applied to the
	Event Channel. The prescaler value factor must be greater than or equal to 1.
	The mode parameter is defined as follows: 0x00 stops specified DAQ list, 0x01 starts
	specified DAQ list, 0x02 prepares DAQ list for synchronised start.
	The start/stop mode parameter = 0x02 (prepare to start data transmission) configures the
	DAQ list with the provided parameters but does not start the data acquisition of the
	specified list. This parameter is used for a synchronized start of all configured DAQ lists. In
	case the slave device is not capable of performing the synchronized start of the data
	acquisition, the slave device may then start data transmission if this parameter is TRUE
	(not zero).
	The ECU specific properties of event channels and DAQ lists may be described in the slave
	device description (ASAP2).

	:param mode: start / stop / prepare data transmission
	:param daq_list_number: DAQ list number
	:param last_odt_number: Last ODT number
	:param event_channel: Event channel number
	:param prescaler: Transmission rate prescaler - word
	'''
	code = 0x06

	def init (self, mode: DataTransmissionMode, daq_list_number: int, last_odt_number: int, event_channel: int, prescaler: int) -> None:
		self.data = bytes([mode.value, daq_list_number, last_odt_number, event_channel]) + prescaler.to_bytes(2, 'little')

class Disconnect(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	Disconnects the slave device. The disconnect can be temporary, setting the slave device in
	an "off line" state or with parameter 0x01 terminating the calibration session.
	Terminating the session invalidates all state information and resets the slave protection
	status.
	A temporary disconnect doesn’t stop the transmission of DAQ messages. The MTA values,
	the DAQ setup, the session status and the protection status are unaffected by the
	temporary disconnect and remain unchanged.
	If the ECU supports the resume feature and the resume bit was set with a
	SET_SESSION_STATUS command, the DAQ related functions behave like in a temporary
	disconnect. The protections status for DAQ remains unlocked.

	:param disconnect_type: Temporary or end of session
	:param station_address: station address, word
	'''
	code = 0x07

	def init (self, disconnect_type: DisconnectType, station_address: int) -> None:
		self.data = disconnect_type.value.to_bytes(1, 'little') + station_address.to_bytes(2, 'little')

class SetSessionStatus(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	Keeps the slave node informed about the current state of the calibration session (see also
	chapter 'Error Handling').

	Bits are set (1) if expression is TRUE.
	The session status bits are read/write to the slave device and are be cleared on power-up,
	on session log-off and in applicable fault conditions.

	Session status, LSB:
	RUN | STORE | res | res | res | RESUME | DAQ | CAL

	bit 0: CAL - Calibration data initialized
	bit 1: DAQ - DAQ lists initialized 
	bit 2: RESUME - Request to save DAQ setup during shutdown in ECU. ECU automatically restarts DAQ after startup
	bit 3: res - reserved
	bit 4: res - reserved
	bit 5: res - reserved
	bit 6: STORE - Request to save calibration data during shut-down in ECU
	bit 7: RUN - Session in progress 

	:param status_bits: Session status bits. See table above 
	'''
	code = 0x0C

	def init (self, status: Union[int, SessionStatusBitfield]) -> None:
		if isinstance(status, SessionStatusBitfield):
			status = bytes(status)
		else:
			status = status.to_bytes(1, 'little')

		self.data = status

class GetSessionStatus(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	Note: the use of additional status information is manufacturer and / or project specific, it
	is not part of this protocol specification. For example, additional status information could
	contain an incremental checksum result, that keeps track of the current session activities.
	If the return information does not contain additional status information, the additional
	status information qualifier has to be FALSE (0). If the additional status information is not
	FALSE, it may be used to determine the type of additional status information
	'''
	code = 0x0D

class BuildChecksum(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	Returns a checksum result of the memory block that is defined by MTA0
	(memory transfer area start address) and block size. The checksum algorithm
	may be manufacturer and / or project specific, it is not part of this specification.

	:param size: block size in bytes - unsigned long
	'''
	code = 0x0E

	def init (self, size: int) -> None:
		self.data = size.to_bytes(4, 'little') # @todo not sure about LSB here

class ClearMemory(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	This command may be used to erase FLASH EPROM prior to reprogramming. The MTA0
	pointer points to the memory location to be erased.

	:param size: memory size - long
	'''
	code = 0x10

	def init (self, size: int) -> None:
		self.data = size.to_bytes(4, 'little')

class Program(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	The data block of the specified length (size) contained in the CRO will be programmed into
	non-volatile memory (FLASH, EEPROM), starting at current MTA0. The MTA0 pointer will
	be post-incremented by the value of ‘size’.

	:param size: size of data block to follow (max 5) 
	:param data: data to be programmed
	'''
	code = 0x18

	def init (self, size: int, data: bytes) -> None:
		if size > 5:
			raise ValueError(f'Invalid requested size: {size}. Maximum value is 5')

		if len(data) > 5:
			raise ValueError('Invalid data size. Maximum length is 5')

		self.data = size.to_bytes(1, 'little') + data

class Program6Bytes(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	The data block with the length (size) of 6 bytes contained in the CRO will be programmed
	into non-volatile memory (FLASH, EEPROM), starting at current MTA0. The MTA0 pointer
	will be post-incremented by 6.

	:param data: data to be programmed (6 bytes)
	'''
	code = 0x22

	def init (self, data: bytes) -> None:
		if len(data) > 6:
			raise ValueError('Invalid data size. Maximum length is 6')

		self.data = data

class MoveMemoryBlock(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	A data block of the specified length (size) will becopied from the address defined by MTA 0
	(source pointer) to the address defined by MTA 1 (destination pointer).

	:param size: number of bytes to be moved (size of the data block) - long
	'''
	code = 0x19

	def init (self, size: int) -> None:
		self.data = size.to_bytes(4, 'little')

class DiagnosticService(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	The slave device carries out the requested service and automatically sets the Memory
	Transfer Address MTA0 to the location from which the CCP master device (host) may
	subsequently upload the requested diagnostic service return information.

	:param service_number: Diagnostic service number - word
	'''
	code = 0x20

	def init (self, service_number: int) -> None:
		self.data = service_number.to_bytes(2, 'little')

class ActionService(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	The slave device carries out the requested service and automatically sets the Memory
	Transfer Address MTA0 to the location from which the CCP master device may
	subsequently upload the requested action service return information (if applicable).

	:param service_number: Action service number - word
	:param parameters: parameters, if applicable
	'''
	code = 0x21 

	def init (self, service_number: int, parameters: bytes = bytes()) -> None:
		self.data = service_number.to_bytes(2, 'little') + parameters

class TestAvailability(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	This command is used to test if the slave with the specified station address is
	available for CCP communication. This command does not establish a logical
	connection nor does it trigger any activities in the specified slave. Station
	address is specified as a number in little-endian byte order (Intel format, low
	byte first).

	:param station_address: station address, word. 
	'''
	code = 0x05

	def init (self, station_address: int) -> None:
		self.data = station_address.to_bytes(2, 'little')

class StartStopSynchronisedDataTransmission(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:
	
	This command is used to start the periodic transmission of all DAQ lists
	configured with the previously sent START_STOP command (start/stop modus
	= 2) as „prepared to start“ in a synchronized manner. The command is used to
	stop the periodic transmission of all DAQ lists, including those not started
	synchronized.

	:param request: Stop/Start data transmission
	'''
	code = 0x08

	def init (self, request: DataTransmissionRequest) -> None:
		self.data = request.value.to_bytes(1, 'little')

class GetCurrentlyActiveCalibrationPage(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	This command returns the start address of the calibration page that is currently active in the
	slave device.
	'''
	code = 0x09

class GetImplementedVersionOfCcp(CcpCommand):
	'''
	Copied placeholder, to be translated from ISO to human:

	This command performs a mutual identification of the protocol version used in the
	master and in the slave device to aggree on a common protocol version. This
	command is expected to be executed prior to the EXCHANGE_ID command.

	:param main_protocol_version: Desired main protocol version
	:param release_protocol_version: Desired release within version
	'''
	code = 0x1B

	def init (self, main_protocol_version: int, release_protocol_version: int) -> None:
		self.data = bytes([main_protocol_version, release_protocol_version])