'''
ctypes binding of a J2534 PassThru library (DLL on Windows, shared object elsewhere)
'''

import ctypes
import logging
import platform
import struct
import sys
from collections.abc import Sequence
from ctypes import (
	POINTER,
	Structure,
	byref,
	c_char_p,
	c_long,
	c_ubyte,
	c_ulong,
	c_void_p,
	create_string_buffer,
)
from dataclasses import dataclass
from typing import Any

from ...exceptions import (
	ChannelException,
	ChannelNotSupportedException,
	GkbusException,
	OpeningChannelException,
	TimeoutException,
)
from .constants import MSG_DATA_MAX, Ioctl, Status

logger = logging.getLogger(__name__)

#: J2534 asks for 80 byte text buffers, some libraries write more
TEXT_BUFFER_SIZE = 256


class PassThruMsg(Structure):
	# unsigned long, like the libraries: 4 bytes on Windows, 8 on 64 bit Linux and macOS
	_fields_ = (
		('ProtocolID', c_ulong),
		('RxStatus', c_ulong),
		('TxFlags', c_ulong),
		('Timestamp', c_ulong),
		('DataSize', c_ulong),
		('ExtraDataIndex', c_ulong),
		('Data', c_ubyte * MSG_DATA_MAX),
	)

class SConfig(Structure):
	_fields_ = (('Parameter', c_ulong), ('Value', c_ulong))

class SConfigList(Structure):
	_fields_ = (('NumOfParams', c_ulong), ('ConfigPtr', POINTER(SConfig)))

@dataclass(frozen=True)
class J2534Message:
	'''
	A PASSTHRU_MSG. For CAN and ISO 15765 the data starts with the 4 byte big endian CAN id
	'''
	protocol: int
	data: bytes
	rx_status: int = 0
	tx_flags: int = 0
	timestamp: int = 0

	def to_struct (self, msg: PassThruMsg | None = None) -> PassThruMsg:
		if len(self.data) > MSG_DATA_MAX:
			raise ValueError('J2534 message too long: {} bytes'.format(len(self.data)))
		msg = msg if msg is not None else PassThruMsg()
		msg.ProtocolID = self.protocol
		msg.RxStatus = self.rx_status
		msg.TxFlags = self.tx_flags
		msg.Timestamp = self.timestamp
		msg.DataSize = len(self.data)
		msg.ExtraDataIndex = len(self.data)
		ctypes.memmove(msg.Data, self.data, len(self.data))
		return msg

	@classmethod
	def from_struct (cls, msg: PassThruMsg) -> 'J2534Message':
		size = min(msg.DataSize, MSG_DATA_MAX)
		return cls(
			protocol=msg.ProtocolID,
			data=ctypes.string_at(ctypes.addressof(msg.Data), size),
			rx_status=msg.RxStatus,
			tx_flags=msg.TxFlags,
			timestamp=msg.Timestamp,
		)

class J2534Error(GkbusException):
	'''
	A PassThru call failed. The subclasses are also the matching gkbus exceptions,
	e.g. J2534TimeoutError is a TimeoutException
	'''

	def __init__ (self, function: str, status: int, description: str = '') -> None:
		self.function = function
		self.status = status
		self.description = description
		message = '{} failed: {}'.format(function, status_name(status))
		if description and not self._repeats(description):
			message += ' ({})'.format(description)
		super().__init__(message)

	def _repeats (self, description: str) -> bool:
		'''
		Whether the library's description says nothing but the function and status
		'''
		rest = description.replace(status_name(self.status), '').strip(' :')
		return self.function.startswith(rest)

class J2534ChannelError(J2534Error, ChannelException):
	pass

class J2534TimeoutError(J2534Error, TimeoutException):
	pass

class J2534OpeningError(J2534Error, OpeningChannelException):
	pass

class J2534NotSupportedError(J2534Error, ChannelNotSupportedException):
	pass

ERROR_TYPES: dict[int, type[J2534Error]] = {
	Status.ERR_TIMEOUT: J2534TimeoutError,
	Status.ERR_BUFFER_EMPTY: J2534TimeoutError,
	Status.ERR_NO_FLOW_CONTROL: J2534TimeoutError,
	Status.ERR_NOT_SUPPORTED: J2534NotSupportedError,
	Status.ERR_INVALID_PROTOCOL_ID: J2534NotSupportedError,
	Status.ERR_PIN_INVALID: J2534NotSupportedError,
	Status.ERR_DEVICE_NOT_CONNECTED: J2534OpeningError,
	Status.ERR_DEVICE_IN_USE: J2534OpeningError,
	Status.ERR_CHANNEL_IN_USE: J2534OpeningError,
}

def status_name (status: int) -> str:
	try:
		return Status(status).name
	except ValueError:
		return 'status 0x{:02X}'.format(status)

def error_for (function: str, status: int, description: str = '') -> J2534Error:
	return ERROR_TYPES.get(status, J2534ChannelError)(function, status, description)

#: name: argument types of the 14 J2534 functions
FUNCTIONS: dict[str, list[Any]] = {
	'PassThruOpen': [c_void_p, POINTER(c_ulong)],
	'PassThruClose': [c_ulong],
	'PassThruConnect': [c_ulong, c_ulong, c_ulong, c_ulong, POINTER(c_ulong)],
	'PassThruDisconnect': [c_ulong],
	'PassThruReadMsgs': [c_ulong, POINTER(PassThruMsg), POINTER(c_ulong), c_ulong],
	'PassThruWriteMsgs': [c_ulong, POINTER(PassThruMsg), POINTER(c_ulong), c_ulong],
	'PassThruStartPeriodicMsg': [c_ulong, POINTER(PassThruMsg), POINTER(c_ulong), c_ulong],
	'PassThruStopPeriodicMsg': [c_ulong, c_ulong],
	'PassThruStartMsgFilter': [
		c_ulong, c_ulong, POINTER(PassThruMsg), POINTER(PassThruMsg), POINTER(PassThruMsg),
		POINTER(c_ulong),
	],
	'PassThruStopMsgFilter': [c_ulong, c_ulong],
	'PassThruSetProgrammingVoltage': [c_ulong, c_ulong, c_ulong],
	'PassThruReadVersion': [c_ulong, c_char_p, c_char_p, c_char_p],
	'PassThruGetLastError': [c_char_p],
	'PassThruIoctl': [c_ulong, c_ulong, c_void_p, c_void_p],
}

#: IMAGE_FILE_MACHINE_* of PE files
PE_MACHINES = {0x014C: 'x86', 0x8664: 'x64', 0xAA64: 'arm64'}

def library_machine (path: str) -> str | None:
	'''
	Architecture a Windows DLL was built for, read from its PE header

	:return: x86, x64, arm64, or None if it couldn't be read
	'''
	try:
		with open(path, 'rb') as file:
			header = file.read(0x40)
			if len(header) < 0x40 or header[:2] != b'MZ':
				return None
			file.seek(struct.unpack_from('<I', header, 0x3C)[0])
			pe = file.read(6)
	except (OSError, struct.error):
		return None
	if len(pe) < 6 or pe[:4] != b'PE\0\0':
		return None
	return PE_MACHINES.get(struct.unpack_from('<H', pe, 4)[0])

def python_machine () -> str:
	'''
	Architecture of the running Python, named like library_machine() does
	'''
	if struct.calcsize('P') == 4:
		return 'x86'
	return 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'x64'

class J2534Library:
	'''
	A loaded J2534 library. Thin wrapper around the PassThru functions: takes and returns
	Python types, raises J2534Error (with the library's own error text) when a call fails
	'''

	def __init__ (self, path: str) -> None:
		'''
		:raises OpeningChannelException: the library can't be loaded or isn't a J2534 library
		'''
		self.path = path
		self._dll = self._load(path)
		try:
			for name, argtypes in FUNCTIONS.items():
				function = getattr(self._dll, name)
				function.argtypes = argtypes
				function.restype = c_long
		except AttributeError as e:
			raise OpeningChannelException(
				'{} is not a J2534 library: {}'.format(path, e)
			) from e

	@staticmethod
	def _load (path: str) -> ctypes.CDLL:
		try:
			if sys.platform == 'win32':
				return ctypes.WinDLL(path)
			return ctypes.CDLL(path)
		except OSError as e:
			machine = library_machine(path) if sys.platform == 'win32' else None
			if machine is not None and machine != python_machine():
				raise OpeningChannelException(
					'J2534 library {} is {}, this Python is {} - it can only load {} libraries'
					.format(path, machine, python_machine(), python_machine())
				) from e
			raise OpeningChannelException(
				'Loading J2534 library {} failed: {}'.format(path, e)
			) from e

	def open (self, name: str | None = None) -> int:
		'''
		:param name: device name, None for the library's default device
		:return: device id
		'''
		device_id = c_ulong()
		self._call('PassThruOpen', name.encode() if name else None, byref(device_id))
		return device_id.value

	def close (self, device_id: int) -> None:
		self._call('PassThruClose', device_id)

	def connect (self, device_id: int, protocol: int, flags: int, baudrate: int) -> int:
		'''
		:return: channel id
		'''
		channel_id = c_ulong()
		self._call('PassThruConnect', device_id, protocol, flags, baudrate, byref(channel_id))
		return channel_id.value

	def disconnect (self, channel_id: int) -> None:
		self._call('PassThruDisconnect', channel_id)

	def read_msgs (self, channel_id: int, count: int, timeout_ms: int) -> list[J2534Message]:
		'''
		Read up to `count` messages, waiting up to timeout_ms for them

		:return: the messages that arrived, possibly none
		'''
		buffer = (PassThruMsg * count)()
		read = c_ulong(count)
		status = self._dll.PassThruReadMsgs(channel_id, buffer, byref(read), timeout_ms)
		messages = [J2534Message.from_struct(buffer[i]) for i in range(min(read.value, count))]
		if status == Status.ERR_BUFFER_OVERFLOW:
			# the messages that made it are still good
			logger.warning('J2534 receive queue overran, messages were lost: {}'.format(
				self.last_error()
			))
		elif status not in (Status.NOERROR, Status.ERR_BUFFER_EMPTY, Status.ERR_TIMEOUT):
			raise self._error('PassThruReadMsgs', status)
		return messages

	def write_msgs (
		self,
		channel_id: int,
		messages: Sequence[J2534Message],
		timeout_ms: int,
	) -> None:
		'''
		:param timeout_ms: time for all of them to go out, 0 - queue them and return at once
		'''
		buffer = (PassThruMsg * len(messages))()
		for i, message in enumerate(messages):
			message.to_struct(buffer[i])
		count = c_ulong(len(messages))
		self._call('PassThruWriteMsgs', channel_id, buffer, byref(count), timeout_ms)

	def start_msg_filter (
		self,
		channel_id: int,
		filter_type: int,
		mask: J2534Message,
		pattern: J2534Message,
		flow_control: J2534Message | None = None,
	) -> int:
		'''
		:return: filter id
		'''
		filter_id = c_ulong()
		self._call(
			'PassThruStartMsgFilter',
			channel_id,
			filter_type,
			byref(mask.to_struct()),
			byref(pattern.to_struct()),
			byref(flow_control.to_struct()) if flow_control is not None else None,
			byref(filter_id),
		)
		return filter_id.value

	def stop_msg_filter (self, channel_id: int, filter_id: int) -> None:
		self._call('PassThruStopMsgFilter', channel_id, filter_id)

	def set_programming_voltage (self, device_id: int, pin: int, voltage: int) -> None:
		'''
		:param voltage: millivolts, SHORT_TO_GROUND or VOLTAGE_OFF
		'''
		self._call('PassThruSetProgrammingVoltage', device_id, pin, voltage)

	def read_version (self, device_id: int) -> tuple[str, str, str]:
		'''
		:return: firmware, library and API version
		'''
		buffers = [create_string_buffer(TEXT_BUFFER_SIZE) for _ in range(3)]
		self._call('PassThruReadVersion', device_id, *buffers)
		firmware, library, api = (self._text(x) for x in buffers)
		return firmware, library, api

	def last_error (self) -> str:
		'''
		The library's description of the last failed call, empty if it has none
		'''
		buffer = create_string_buffer(TEXT_BUFFER_SIZE)
		try:
			if self._dll.PassThruGetLastError(buffer) != Status.NOERROR:
				return ''
		except OSError:
			return ''
		return self._text(buffer)

	def ioctl (self, channel_id: int, ioctl_id: int, data_in: object, data_out: object) -> None:
		'''
		:param data_in: pointer (byref) or None
		:param data_out: pointer (byref) or None
		'''
		self._call(
			'PassThruIoctl', channel_id, ioctl_id, data_in, data_out, name=Ioctl(ioctl_id).name,
		)

	def get_config (self, channel_id: int, parameter: int) -> int:
		config = SConfig(parameter, 0)
		config_list = SConfigList(1, ctypes.pointer(config))
		self.ioctl(channel_id, Ioctl.GET_CONFIG, byref(config_list), None)
		return int(config.Value)

	def set_config (self, channel_id: int, parameter: int, value: int) -> None:
		config = SConfig(parameter, value)
		config_list = SConfigList(1, ctypes.pointer(config))
		self.ioctl(channel_id, Ioctl.SET_CONFIG, byref(config_list), None)

	def read_vbatt (self, device_id: int) -> int:
		'''
		:return: battery voltage (OBD pin 16) in millivolts
		'''
		voltage = c_ulong()
		self.ioctl(device_id, Ioctl.READ_VBATT, None, byref(voltage))
		return voltage.value

	def fast_init (self, channel_id: int, request: J2534Message) -> bytes:
		'''
		ISO 14230 fast init followed by the request

		:return: the ECU's response
		'''
		response = PassThruMsg()
		self.ioctl(channel_id, Ioctl.FAST_INIT, byref(request.to_struct()), byref(response))
		return J2534Message.from_struct(response).data

	def clear_rx_buffer (self, channel_id: int) -> None:
		self.ioctl(channel_id, Ioctl.CLEAR_RX_BUFFER, None, None)

	def clear_tx_buffer (self, channel_id: int) -> None:
		self.ioctl(channel_id, Ioctl.CLEAR_TX_BUFFER, None, None)

	def _call (self, function: str, *args: object, name: str | None = None) -> None:
		status = getattr(self._dll, function)(*args)
		if status != Status.NOERROR:
			raise self._error('{}({})'.format(function, name) if name else function, status)

	def _error (self, function: str, status: int) -> J2534Error:
		return error_for(function, status, self.last_error())

	@staticmethod
	def _text (buffer: ctypes.Array[ctypes.c_char]) -> str:
		return buffer.value.decode('ascii', errors='replace').strip()
