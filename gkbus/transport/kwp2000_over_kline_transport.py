import logging

from ..channel import KLineChannel
from ..exceptions import TimeoutException
from .transport_abc import PacketDirection, TransportABC

logger = logging.getLogger(__name__)

#: how long to wait for each frame the ECU sends in response to fast init
FAST_INIT_DRAIN_TIMEOUT = 0.4
#: most frames drained after fast init
FAST_INIT_DRAIN_FRAMES = 3

class Kwp2000OverKLineTransport (TransportABC):
	'''
	KWP2000 over K-Line (ISO 14230): every PDU is wrapped in a frame with a length byte,
	target and source addresses and a checksum
	'''

	channel: KLineChannel

	def __init__ (self, channel: KLineChannel, tx_id: int, rx_id: int, timeout: float = 2) -> None:
		'''
		:param channel: K-Line channel, e.g. from device.kline()
		:param tx_id: target address (the ECU)
		:param rx_id: source address (the tester)
		:param timeout: seconds to wait for a response
		'''
		super().__init__(channel, tx_id, rx_id, timeout)

	def send_pdu (self, pdu: bytes) -> int:
		data = self.build_payload(pdu)

		self._write(data)
		self._record(PacketDirection.OUTGOING, data)

		return len(pdu)

	def read_pdu (self, timeout: float | None = None) -> bytes:
		timeout = self._timeout(timeout)
		frame = bytes()
		data = bytes()

		frame += self._read(4, timeout)

		counter = frame[0]

		# more than 127 bytes incoming, counter overflowed. counter is gonna come after IDs
		if (counter == 0x80):
			counter = frame[3]+1
			logger.debug('More than 127 bytes incoming: {}'.format(counter))
		else:
			counter = counter-0x80
			# frame[3] == python would automatically convert it to int. frame[3:4] == byte slice
			data += frame[3:4]

		data_and_checksum = self._read(counter, timeout)
		frame += data_and_checksum
		data += data_and_checksum[:-1] # last byte is the checksum

		self._record(PacketDirection.INCOMING, frame)

		return data

	def init (self, init_pdu: bytes | None = None) -> bool:
		'''
		Open the channel if not opened already and, if a StartCommunication PDU is provided,
		wake up the ECU with ISO14230 fast init.

		Responses to the fast init are drained and timeouts are ignored - the first
		real request will tell whether the ECU is listening.

		:param init_pdu: StartCommunication PDU to send as part of the fast init
		'''
		self.open()

		if init_pdu is None:
			return True

		self.channel.fast_init(self.build_payload(init_pdu))
		try:
			for _ in range(FAST_INIT_DRAIN_FRAMES):
				self.read_pdu(timeout=FAST_INIT_DRAIN_TIMEOUT)
		except TimeoutException:
			pass

		return True

	def calculate_checksum (self, payload: bytes) -> int:
		return sum(payload) & 0xFF

	def build_payload (self, data: bytes) -> bytes:
		data_length = len(data)

		if (data_length < 127):
			counter = 0x80 + data_length
		else:
			counter = 0x80
			data = bytes([data_length]) + data

		payload = bytes([counter, self.tx_id, self.rx_id])
		payload += data
		payload += self.calculate_checksum(payload).to_bytes(1, 'big')

		return payload

	def _write (self, data: bytes) -> int:
		logger.debug('K-Line sending: {}'.format(' '.join([hex(x) for x in list(data)])))
		return self.channel.write(data)

	def _read (self, length: int, timeout: float) -> bytes:
		logger.debug('K-Line trying to read {} bytes'.format(length))
		data = self.channel.read(length, timeout)
		logger.debug('K-Line success: {}'.format(' '.join([hex(x) for x in list(data)])))
		return data
