from dataclasses import dataclass
from enum import Enum, auto


class CcpReturnCodeCategory (Enum):
	'''
	Return codes in CCP are grouped into categories. 
	SUCCESS category doesn't exist in theory, 0x00 ACKNOWLEDGE 
	response doesn't have a category assigned. SUCCESS was added 
	for code clarity

	'''
	SUCCESS = auto()
	'''Added for code clarity'''

	WARNING = auto()
	'''C0 - Warning'''

	SPURIOUS = auto()
	'''C1 - Spurious (comm error, busy, ...). Action: wait (ACK or timeout)'''

	RESOLVABLE = auto()
	'''C2 - Resolvable (temp. power loss, ...). Action: reinitialize'''

	UNRESOLVABLE = auto()
	'''C3 - Unresolvable (setup, overload, ...). Action: terminate'''

class CcpReturnCodeCategoryMap (Enum):
	ACKNOWLEDGE = CcpReturnCodeCategory.SUCCESS
	DAQ_PROCESSOR_OVERLOAD = CcpReturnCodeCategory.WARNING
	COMMAND_PROCESSOR_BUSY = CcpReturnCodeCategory.SPURIOUS
	DAQ_PROCESSOR_BUSY = CcpReturnCodeCategory.SPURIOUS
	INTERNAL_TIMEOUT = CcpReturnCodeCategory.SPURIOUS
	KEY_REQUEST = CcpReturnCodeCategory.SPURIOUS
	SESSION_STATUS_REQUEST = CcpReturnCodeCategory.SPURIOUS
	COLD_START_REQUEST = CcpReturnCodeCategory.RESOLVABLE
	CAL_DATA_INIT_REQUEST = CcpReturnCodeCategory.RESOLVABLE
	DAQ_LIST_INIT_REQUEST = CcpReturnCodeCategory.RESOLVABLE
	CODE_UPDATE_REQUEST = CcpReturnCodeCategory.RESOLVABLE
	UNKNOWN_COMMAND = CcpReturnCodeCategory.UNRESOLVABLE
	COMMAND_SYNTAX = CcpReturnCodeCategory.UNRESOLVABLE
	PARAMETERS_OUT_OF_RANGE = CcpReturnCodeCategory.UNRESOLVABLE
	ACCESS_DENIED = CcpReturnCodeCategory.UNRESOLVABLE
	OVERLOAD = CcpReturnCodeCategory.UNRESOLVABLE
	ACCESS_LOCKED = CcpReturnCodeCategory.UNRESOLVABLE
	RESOURCE_NOT_AVAILABLE = CcpReturnCodeCategory.UNRESOLVABLE

class CcpReturnCode (Enum):
	ACKNOWLEDGE = 0x00
	DAQ_PROCESSOR_OVERLOAD = 0x01
	COMMAND_PROCESSOR_BUSY = 0x10
	DAQ_PROCESSOR_BUSY = 0x11
	INTERNAL_TIMEOUT = 0x12
	KEY_REQUEST = 0x18
	SESSION_STATUS_REQUEST = 0x19
	COLD_START_REQUEST = 0x20
	CAL_DATA_INIT_REQUEST = 0x21
	DAQ_LIST_INIT_REQUEST = 0x22
	CODE_UPDATE_REQUEST = 0x23
	UNKNOWN_COMMAND = 0x30
	COMMAND_SYNTAX = 0x31
	PARAMETERS_OUT_OF_RANGE = 0x32
	ACCESS_DENIED = 0x33
	OVERLOAD = 0x34
	ACCESS_LOCKED = 0x35
	RESOURCE_NOT_AVAILABLE = 0x36

	@property
	def category(self) -> CcpReturnCodeCategory:
		return CcpReturnCodeCategoryMap[self.name].value

	@property
	def success (self) -> bool:
		return self.category == CcpReturnCodeCategory.SUCCESS

	def __str__ (self) -> str:
		return 'CcpReturnCode(code={}, name={}, category={})'.format(hex(self.value), self.name, self.category.name)

	def __repr__ (self) -> str:
		return self.__str__()

@dataclass
class CcpResponseFrame:
	'''
	Also known as Data Transmission Object - DTO. 
	Perhaps this should be renamed
	
	Structure:
	1 byte - data packet ID = PID.
		0xFF - DTO contains a Command Return Message
		0xFE - DTO contains an Event Message. Counter is ignored
		0 < x < 0xFD - DTO contains a Data Acquisition Message corresponding to ODT n
	1 byte - status - command return / error code
	1 byte - counter of transmitted frames (from slave to master)
	5 bytes - data 
	'''
	packet_id: int
	status: int
	counter: int
	data: bytes

	def __str__ (self) -> str:
		return 'CcpResponseFrame({})'.format(' '.join([hex(x)[2:].zfill(2) for x in list(self.data)]))

	def __repr__ (self) -> str:
		return self.__str__()

@dataclass
class CcpResponse:
	return_code: CcpReturnCode
	frame: CcpResponseFrame 

	def success (self) -> bool: # @todo: should this be removed, considering we have it already in return_code?
		return self.return_code.success

	def get_data (self) -> bytes: # todo: deprecate?
		return self.frame.data
