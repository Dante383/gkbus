import logging
from typing import Union
from dataclasses import dataclass
from ..protocol_abc import ProtocolABC
from ...transport import Kwp2000OverKLineTransport
from ...hardware import TimeoutException
from .kwp2000_command import Kwp2000Command
from .kwp2000_response import Kwp2000ResponseFrame, Kwp2000Response
from .kwp2000_negative_status import Kwp2000NegativeStatus

logger = logging.getLogger(__name__)

class Kwp2000Exception(Exception):
	pass

class Kwp2000NegativeResponseException(Exception):
	def __init__ (self, status: Kwp2000NegativeStatus) -> None:
		self.status = status

	def __str__ (self) -> str:
		return '{} - {}'.format(hex(self.status.identifier), self.status.message)
	
	def __repr__ (self) -> str:
		return self.__str__()

@dataclass
class Kwp2000RequestFrame:
	service_identifier: int
	data: bytes

	def to_pdu (self) -> bytes:
		return self.service_identifier.to_bytes(1, 'big') + self.data

class Kwp2000Protocol (ProtocolABC):
	STATUS_ECU_BUSY_RESPONSE_PENDING: int = 0x78

	def init (self, init_command: Kwp2000Command) -> bool:
		if not isinstance(self.transport, Kwp2000OverKLineTransport):
			return True

		init_payload = Kwp2000RequestFrame(init_command.get_service_identifier(), init_command.get_data(as_list=False))

		try:
			self.transport.hardware.set_timeout(0.4)
			(response, time_low, time_high) = self.transport.init(init_payload.to_pdu())
			logger.debug('K-Line FastInit: success: {}, time low: {}, time high: {}'.format(response, time_low, time_high))
			self.transport.read_pdu()
			self.transport.hardware.set_timeout(2)
			return True
		except TimeoutException:
			logger.warning('K-Line fast init failed')

		self.transport.hardware.set_timeout(2)

		return False


	def execute (self, command: Kwp2000Command) -> Kwp2000Response:
		frame = Kwp2000RequestFrame(command.get_service_identifier(), command.get_data(as_list=False))

		response_pdu = self.transport.send_read_pdu(data=frame.to_pdu())
		response = self.handle_errors(
			Kwp2000Response(Kwp2000ResponseFrame(status=response_pdu[0], data=response_pdu[1:]))
		)

		return response

	def handle_errors (self, response: Kwp2000Response) -> Union[None, Kwp2000Response]:
		if response.success():
			return response

		if response.frame.data[0] == self.STATUS_ECU_BUSY_RESPONSE_PENDING:
			logger.info('ECU is busy, request received, response pending.')

			response_pdu = self.transport.read_pdu()
			return self.handle_errors(Kwp2000Response(Kwp2000ResponseFrame(status=response_pdu[0], data=response_pdu[1:])))

		raise Kwp2000NegativeResponseException(Kwp2000NegativeStatus(identifier=response.frame.data[1]))