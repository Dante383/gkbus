import time, sys, logging
import serial
import serial.tools.list_ports
from typing import List

logger = logging.getLogger(__name__)

class KLineSerial:
	TIMEOUT_AFTER_REQUEST = (30 + 20)/1000

	def __init__ (self, iface, baudrate):
		self.iface, self.baudrate = iface, baudrate
		try:
			self.socket = serial.Serial(iface, baudrate, timeout=0.4)
			self.reset_adapter()
			self.set_adapter_KKL()
		except serial.serialutil.SerialException:
			print('[!] Device {} not found! Available devices:\n'.format(iface))
			print('\n'.join([device[1] + ':' + device[0] for device in KLineSerial.available_devices()]))
			sys.exit(1)
	
	def reset_adapter(self):
		"""Reset the adapter by toggling DTR."""
		self.socket.setDTR(1)
		time.sleep(0.1)
		self.socket.setDTR(0)
		time.sleep(0.1)

	def set_adapter_KKL(self):
		"""Set adapter to KKL mode."""
		self.socket.setDTR(0)
		self.socket.setRTS(0)
		time.sleep(0.1)

	def fast_init_native(self, payload: List[int]):
		"""FastInit Low (hold break_condition = True for 25 ms)"""
		start_time = time.perf_counter()
		self.socket.break_condition = True
		self.socket.flush()  # Ensure the break is sent immediately
		while (time.perf_counter() - start_time) < 0.025:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_low = time.perf_counter() - start_time

		"""FastInit High (hold break_condition = False for 25 ms)"""
		start_time = time.perf_counter()
		self.socket.break_condition = False
		self.socket.flush()  # Ensure the break is sent immediately
		while (time.perf_counter() - start_time) < 0.025:
			pass  # Busy-wait until 25 ms has passed
		elapsed_time_high = time.perf_counter() - start_time
		
		# Send payload and read response
		self.socket.write(bytes(payload))
		response = self.socket.read(1)

		return response, elapsed_time_low, elapsed_time_high

	def write (self, payload):
		time.sleep(self.TIMEOUT_AFTER_REQUEST*2)
		self.socket.write(payload)

		while self.socket.out_waiting > 0:
			time.sleep(0.001)

		self.read(len(payload))

	def read (self, length):
		message = self.socket.read(length)
		return message

	def shutdown (self) -> None:
		try:
			self.socket.break_condition = False
			self.socket.close()
		except AttributeError:
			pass

	@staticmethod
	def available_devices () -> List: # [description, url]
		devices = []
		for port in reversed(serial.tools.list_ports.comports()):
			devices.append(("{}: {} {}".format(port.name, port.manufacturer, port.serial_number), port.device))
		return devices
