import logging
from dataclasses import dataclass

from ...transport import TransportABC
from ..protocol_abc import ProtocolABC, ProtocolException
from .ccp_command import CcpCommand
from .ccp_response import CcpResponse, CcpResponseFrame, CcpReturnCode

logger = logging.getLogger(__name__)

class CcpException(ProtocolException):
	pass

class CcpNegativeResponseException(CcpException):
	def __init__ (self, return_code: CcpReturnCode) -> None:
		self.return_code = return_code

	def __str__ (self) -> str:
		return '{}: {} - {}'.format(self.return_code.category, hex(self.return_code.value), self.return_code.name)
	
	def __repr__ (self) -> str:
		return self.__str__()

@dataclass
class CcpRequestFrame:
	'''
	Also known as Command Receive Object - CRO. 
	Perhaps this should be renamed

	Structure: 
	1 byte - command code 
	1 byte - counter of transmitted frames
	6 bytes - command data
	'''
	command_code: int
	counter: int
	data: bytes

	def to_pdu (self) -> bytes:
		data = self.data + bytes([0x00]*(6-len(self.data))) # padding
		return bytes([self.command_code, self.counter]) + data

class CcpProtocol (ProtocolABC):
	'''
	CAN Calibration Protocol
	'''
	def __init__ (self, transport: TransportABC, byte_order: str = 'little'):
		'''
		CCP protocol doesn't specify byte order for parameters - it depends on the receiving ECU

		:param byte_order: 'little' or 'big'
		'''
		self.transport = transport
		self.byte_order = byte_order
		self.command_counter = 0
		if byte_order != 'little':
			raise NotImplementedError('Byte order switching isn\'t implemented yet. You can resort to manually setting data attribute on commands')

	def open (self) -> bool:
		return self.transport.hardware.open()

	def execute (self, command: CcpCommand) -> CcpResponse:
		frame = CcpRequestFrame(command.get_code(), self.command_counter, command.get_data())

		response_pdu = self.transport.send_read_pdu(data=frame.to_pdu())
		self.command_counter += 1

		if (self.command_counter > 0xFF):
			self.command_counter = 0x00

		response = CcpResponse(
			CcpReturnCode(response_pdu[1]),
			CcpResponseFrame(
				packet_id=response_pdu[0], 
				status=response_pdu[1],
				counter=response_pdu[2],
				data=response_pdu[3:]
				)
			)

		response = self.handle_errors(response)

		return response

	def handle_errors (self, response: CcpResponse) -> CcpResponse:
		if response.success():
			return response

		raise CcpNegativeResponseException(response.return_code)

	def close (self) -> None:
		self.transport.hardware.close()