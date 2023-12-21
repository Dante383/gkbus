import time, logging
from .Interface import InterfaceABC
from .kline.KLineSerial import KLineSerial
from gkbus import GKBusTimeoutException

logger = logging.getLogger(__name__)

class KLineInterface(InterfaceABC):
	socket = False

	def __init__ (self, interface, baudrate, rx_id, tx_id):
		print('    [K] K-line init. Iface: {} baudrate: {}'.format(interface, baudrate))
		self.rx_id = rx_id
		self.tx_id = tx_id
		self.socket = KLineSerial(interface, baudrate=baudrate)

	def init (self) -> None:
		self.socket.init()

	def calculate_checksum (self, payload: list[int]) -> int:
		checksum = 0x0
		for byte in payload:
			checksum += byte
		return checksum & 0xFF

	def build_payload (self, data: list[int]) -> bytearray:
		data_length = len(data)

		if (data_length < 127):
			counter = 0x80 + data_length
		else:
			counter = 0x80
			data = [data_length] + data

		tx_id_b1 = (self.tx_id >> 8) & 0xFF
		tx_id_b2 = (self.tx_id & 0xFF)

		payload = [counter, tx_id_b1, tx_id_b2] + data
		payload += [self.calculate_checksum(payload)]
		return bytes(payload)

	def fetch_response (self) -> list[int]:
		counter = self._read(1)

		if (len(counter) == 0):
			raise GKBusTimeoutException()

		rx_id_b1 = int.from_bytes(self._read(1), "big")
		rx_id_b2 = int.from_bytes(self._read(1), "big")
		rx_id = (rx_id_b1 << 8) | rx_id_b2

		if (counter == b'\x80'): # more than 127 bytes incoming, counter overflowed. counter is gonna come after IDs
			counter = int.from_bytes(self._read(1), "big")
		else:
			counter = int.from_bytes(counter, "big")-0x80

		status = self._read(1)

		data = list(self._read(counter-1))

		checksum = self._read(1)

		if (status == b'\x7F'):
			if (0x78 in data): # ecu is busy. request received, response pending
				logger.warning('ECU is busy, request received, response pending.')
				return self.fetch_response()

		#if (self.calculate_checksum()) todo

		return [int.from_bytes(status, "big")] + data

	def _execute_internal (self, payload: list[int]) -> list[int]:
		self._write(self.build_payload(payload))
		response = self.fetch_response()

		return response

	def _write (self, message: bytearray) -> None:
		logger.debug('K-Line sending: {}'.format(' '.join([hex(x) for x in message])))
		self.socket.write(message)

	def _read (self, length: int) -> bytearray:
		logger.debug('K-Line trying to read {} bytes'.format(length))
		message = self.socket.read(length)
		logger.debug('Success! Received: {}'.format(' '.join([hex(x) for x in message])))
		return message

	def set_timeout (self, timeout: int | None = None):
		if (timeout == None):
			self.socket.socket.timeout = 5
		else:
			self.socket.socket.timeout = timeout
		return self

	def shutdown (self) -> None:
		self.socket.shutdown()