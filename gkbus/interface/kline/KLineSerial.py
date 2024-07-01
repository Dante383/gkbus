import time, sys, logging
import serial
import serial.tools.list_ports
from typing import List

logger = logging.getLogger(__name__)

class KLineSerial:
	HIGH = bytes([0x01])
	LOW = bytes([0x0])

	TIMEOUT_IDLE_BUS_BEFORE_INIT = 3000/1000
	TIMEOUT_POST_INIT = 50/1000
	TIMEOUT_WAIT_FOR_ECHO = 0 #was 5/1000  ms/1000
	TIMEOUT_ECHO_PER_BYTE = 0 #was 3/1000
	TIMEOUT_AFTER_REQUEST = (30 + 20)/1000

	def __init__ (self, iface, baudrate):
		self.iface, self.baudrate = iface, baudrate
		try:
			self.socket = serial.Serial(iface, baudrate, timeout=0.4)
		except serial.serialutil.SerialException:
			print('[!] Device {} not found! Available devices:\n'.format(iface))
			print('\n'.join([device[1] + ':' + device[0] for device in KLineSerial.available_devices()]))
			sys.exit(1)
			
	def fast_init_native (self, payload: List[int]):
		self.socket.break_condition = False # safekeeping
		
		self.socket.break_condition = True
		start = time.monotonic()
		while (time.monotonic() <= start + 0.025):
			time.sleep(0.001)

		self.socket.break_condition = False
		
		start = time.monotonic()
		while (time.monotonic() <= start + 0.025):
			time.sleep(0.001)

		self.socket.write(bytes(payload))
		self.socket.read(1)

	def write (self, payload):
		time.sleep(self.TIMEOUT_AFTER_REQUEST*2)
		self.socket.write(payload)

		while self.socket.out_waiting > 0:
			time.sleep(0.01)

		time.sleep(self.TIMEOUT_WAIT_FOR_ECHO + (self.TIMEOUT_ECHO_PER_BYTE * len(payload)))
		self.read(len(payload))
		time.sleep(self.TIMEOUT_AFTER_REQUEST)

	def read (self, length):
		message = self.socket.read(length)

		return message

	def shutdown (self) -> None:
		try:
			self.socket.close()
		except AttributeError:
			pass

	@staticmethod
	def available_devices () -> List: # [description, url]
		devices = []
		for port in reversed(serial.tools.list_ports.comports()):
			devices.append(("{}: {} {}".format(port.name, port.manufacturer, port.serial_number), port.device))
		return devices