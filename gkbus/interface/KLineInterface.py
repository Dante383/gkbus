import time, logging, struct
from .Interface import InterfaceABC
from .kline.KLineSerial import KLineSerial
from gkbus import GKBusTimeoutException

logger = logging.getLogger(__name__)

class KLineInterface(InterfaceABC):
	
	def __init__ (self, interface, baudrate, rx_id, tx_id):
		self.rx_id, self.tx_id = rx_id, tx_id
		self.socket = KLineSerial(interface, baudrate=baudrate)

	def _init (self, payload) -> None:
		payload = self.build_payload(payload)

		logger.info('fast init native..')
		self.socket.fast_init_native(payload)
		try:
			self.fetch_response()
			self.set_timeout(5)
			return
		except GKBusTimeoutException:
			logger.warning('native fast init failed! trying ftdi fast init..')

		logger.info('fast init ftdi..')
		self.socket.fast_init_ftdi(payload)
		try:
			self.fetch_response()
		except GKBusTimeoutException:
			logger.warning('ftdi fast init failed!')

		self.set_timeout(5)

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

		tx_id = struct.pack('>h', self.tx_id)

		payload = [counter, *tx_id] + data
		payload += [self.calculate_checksum(payload)]
		return bytes(payload)

	def fetch_response (self) -> list[int]:
		counter = self._read(1)

		if (len(counter) == 0):
			raise GKBusTimeoutException()

		rx_id, = struct.unpack('>H', self._read(2))

		if (counter == b'\x80'): # more than 127 bytes incoming, counter overflowed. counter is gonna come after IDs
			counter, = struct.unpack('>B', self._read(1))
		else:
			counter = struct.unpack('>B', counter)[0]-0x80

		status = self._read(1)

		data = list(self._read(counter-1))

		checksum = self._read(1)

		if (status == b'\x7F'):
			if (0x78 in data): 
				logger.warning('ECU is busy, request received, response pending.')
				return self.fetch_response()

		#if (self.calculate_checksum()) todo

		if (rx_id != self.rx_id): # we are only doing this now because we needed to clear this message out of the buffer
			return self.fetch_response()

		return [struct.unpack('>B', status)[0]] + data

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
		try:
			self.socket.shutdown()
		except AttributeError:
			pass
		super().shutdown()