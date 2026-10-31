'''
32 bit J2534 DLLs in a 64 bit Python

Tactrix only ships a 32 bit DLL for the OpenPort 2.0 (op20pt32.dll), which a 64 bit Python
can't load. J2534BridgeLibrary starts a small 32 bit helper process (helper/j2534_helper.c,
built by helper/build.sh) that loads the DLL and makes the PassThru calls for us.

The helper reads requests from its stdin and answers each on its stdout. Integers are
little endian u32.

- request: operation (Op), length of the arguments, the arguments
- response: status, data length, text length, data, text. The status is what the PassThru
  function returned; the text is the library's PassThruGetLastError description when it
  isn't NOERROR (or what went wrong in the helper itself)
- a message: protocol id, rx status, tx flags, timestamp, data size, extra data index, then
  data size bytes of data
'''

import logging
import math
import os
import struct
import subprocess
import threading
import time
import weakref
from collections.abc import Sequence
from ctypes import addressof, c_ulong, memmove, string_at
from enum import IntEnum
from typing import IO, TYPE_CHECKING

from ...exceptions import OpeningChannelException
from .constants import MSG_DATA_MAX, Status
from .library import (
	QUIET_READ_STATUSES,
	IoctlData,
	J2534Error,
	J2534Library,
	J2534Message,
	PassThruMsg,
	SByteArray,
	SConfigList,
	error_for,
	ioctl_name,
)

if TYPE_CHECKING:
	from .registry import J2534LibraryInfo

logger = logging.getLogger(__name__)

HELPER = os.path.join(
	os.path.dirname(os.path.abspath(__file__)), 'helper', 'gkbus_j2534_helper32.exe',
)
MAGIC = 0x424A4B47
VERSION = 1
#: longest the helper waits in one PassThruReadMsgs. Longer reads are split, so calls from
#: other threads don't wait for them
READ_SLICE_MS = 50
#: how long the helper gets to close the adapter and exit before it's killed
STOP_TIMEOUT = 2.0

class Op(IntEnum):
	LOAD = 0
	OPEN = 1
	CLOSE = 2
	CONNECT = 3
	DISCONNECT = 4
	READ_MSGS = 5
	WRITE_MSGS = 6
	START_MSG_FILTER = 7
	STOP_MSG_FILTER = 8
	SET_PROGRAMMING_VOLTAGE = 9
	READ_VERSION = 10
	GET_LAST_ERROR = 11
	IOCTL = 12

class Arg(IntEnum):
	'''
	What PassThruIoctl's input and output pointers point to
	'''
	NONE = 0
	CONFIG_LIST = 1
	MSG = 2
	BYTES = 3
	ULONG = 4

MESSAGE_HEADER = struct.Struct('<6I')
U32 = struct.Struct('<I')

def bridge_available () -> bool:
	'''
	Whether gkbus was installed with the 32 bit helper
	'''
	return os.path.isfile(HELPER)

def load_library (info: 'J2534LibraryInfo') -> J2534Library:
	'''
	Load an installed library: in this process, or in the 32 bit helper if it's a 32 bit DLL
	and this Python is 64 bit

	:raises OpeningChannelException: it can't be loaded
	'''
	if info.bridged():
		logger.debug('Loading {} in the 32 bit helper'.format(info.path))
		return J2534BridgeLibrary(info.path)
	return J2534Library(info.path)

class J2534BridgeLibrary(J2534Library):
	'''
	A J2534 library loaded in the 32 bit helper process. Works like J2534Library;
	calls from several threads take turns
	'''

	def __init__ (self, path: str, command: Sequence[str] | None = None) -> None:
		'''
		:param command: how to start the helper, HELPER by default
		:raises OpeningChannelException: the helper couldn't be started or couldn't load
			the library
		'''
		self.path = path
		self._lock = threading.Lock()
		# threads waiting for _lock, which a read lets go first between its slices
		self._waiting = 0
		self._waiting_lock = threading.Lock()
		command = list(command) if command is not None else [HELPER]
		if command[0] == HELPER and not bridge_available():
			raise OpeningChannelException(
				'{} is a 32 bit J2534 library, loading it in this 64 bit Python needs {}, '
				'which is missing'.format(path, HELPER)
			)
		try:
			process = subprocess.Popen(
				command,
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE,
				creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
			)
		except OSError as e:
			raise OpeningChannelException(
				'Starting the 32 bit J2534 helper {} failed: {}'.format(command[0], e)
			) from e
		self._process: subprocess.Popen[bytes] | None = process
		self._finalizer = weakref.finalize(self, _stop, process)

		try:
			status, _, text = self._request(
				'Loading', Op.LOAD, _u32(MAGIC, VERSION) + path.encode('utf-8'),
			)
		except J2534Error as e:
			self.unload()
			raise OpeningChannelException(
				'Loading J2534 library {} in the 32 bit helper failed: {}'.format(path, e)
			) from e
		if status != Status.NOERROR:
			self.unload()
			raise OpeningChannelException(
				'Loading J2534 library {} in the 32 bit helper failed: {}'.format(path, text)
			)

	def open (self, name: str | None = None) -> int:
		return _unpack_u32(self._rpc(
			'PassThruOpen', Op.OPEN, extra=name.encode() if name else b'',
		))

	def close (self, device_id: int) -> None:
		self._rpc('PassThruClose', Op.CLOSE, device_id)

	def connect (self, device_id: int, protocol: int, flags: int, baudrate: int) -> int:
		return _unpack_u32(self._rpc(
			'PassThruConnect', Op.CONNECT, device_id, protocol, flags, baudrate,
		))

	def disconnect (self, channel_id: int) -> None:
		self._rpc('PassThruDisconnect', Op.DISCONNECT, channel_id)

	def read_msgs (self, channel_id: int, count: int, timeout_ms: int) -> list[J2534Message]:
		'''
		Read up to `count` messages, waiting up to timeout_ms for them. Returns as soon as
		some arrive, which may be fewer than `count`

		:return: the messages that arrived, possibly none
		'''
		deadline = time.monotonic() + timeout_ms / 1000
		while True:
			self._let_others_go()
			remaining = max(0, math.ceil((deadline - time.monotonic()) * 1000))
			wait = min(remaining, READ_SLICE_MS)
			status, data, text = self._request(
				'PassThruReadMsgs', Op.READ_MSGS, _u32(channel_id, count, wait),
			)
			(read,), offset = U32.unpack_from(data), U32.size
			messages = []
			for _ in range(read):
				message, offset = _unpack_message(data, offset)
				messages.append(J2534Message.from_struct(message))
			if messages or status not in QUIET_READ_STATUSES or wait == remaining:
				break
		if status not in QUIET_READ_STATUSES:
			self._check_read(status, text)
		return messages

	def write_msgs (
		self,
		channel_id: int,
		messages: Sequence[J2534Message],
		timeout_ms: int,
	) -> None:
		self._rpc(
			'PassThruWriteMsgs', Op.WRITE_MSGS, channel_id, timeout_ms, len(messages),
			extra=b''.join(_pack_message(x.to_struct()) for x in messages),
		)

	def start_msg_filter (
		self,
		channel_id: int,
		filter_type: int,
		mask: J2534Message,
		pattern: J2534Message,
		flow_control: J2534Message | None = None,
	) -> int:
		messages = [mask, pattern] + ([flow_control] if flow_control is not None else [])
		return _unpack_u32(self._rpc(
			'PassThruStartMsgFilter', Op.START_MSG_FILTER,
			channel_id, filter_type, flow_control is not None,
			extra=b''.join(_pack_message(x.to_struct()) for x in messages),
		))

	def stop_msg_filter (self, channel_id: int, filter_id: int) -> None:
		self._rpc('PassThruStopMsgFilter', Op.STOP_MSG_FILTER, channel_id, filter_id)

	def set_programming_voltage (self, device_id: int, pin: int, voltage: int) -> None:
		self._rpc(
			'PassThruSetProgrammingVoltage', Op.SET_PROGRAMMING_VOLTAGE, device_id, pin, voltage,
		)

	def read_version (self, device_id: int) -> tuple[str, str, str]:
		data = self._rpc('PassThruReadVersion', Op.READ_VERSION, device_id)
		texts, offset = [], 0
		for _ in range(3):
			(size,) = U32.unpack_from(data, offset)
			offset += U32.size
			texts.append(data[offset:offset + size].decode('ascii', errors='replace').strip())
			offset += size
		firmware, library, api = texts
		return firmware, library, api

	def last_error (self) -> str:
		try:
			status, _, text = self._request('PassThruGetLastError', Op.GET_LAST_ERROR, b'')
		except J2534Error:
			return ''
		return text if status == Status.NOERROR else ''

	def ioctl (
		self,
		channel_id: int,
		ioctl_id: int,
		data_in: IoctlData | None = None,
		data_out: IoctlData | None = None,
	) -> None:
		data = self._rpc(
			'PassThruIoctl', Op.IOCTL, channel_id, ioctl_id,
			extra=_ioctl_input(data_in) + _ioctl_output(data_out),
			name=ioctl_name(ioctl_id),
		)
		offset = 0
		if isinstance(data_in, SConfigList):
			(count,) = U32.unpack_from(data, offset)
			offset += U32.size
			for i in range(count):
				data_in.ConfigPtr[i].Value = U32.unpack_from(data, offset + 8 * i + 4)[0]
			offset += 8 * count
		if isinstance(data_out, PassThruMsg):
			_unpack_message(data, offset, data_out)
		elif isinstance(data_out, SByteArray):
			(size,) = U32.unpack_from(data, offset)
			memmove(data_out.BytePtr, data[offset + 4:offset + 4 + size], size)
			data_out.NumOfBytes = size
		elif isinstance(data_out, c_ulong):
			data_out.value = U32.unpack_from(data, offset)[0]

	def unload (self) -> None:
		'''
		Stop the helper. It closes the adapter if it's still open
		'''
		with self._lock:
			self._process = None
		self._finalizer()

	def _rpc (
		self,
		function: str,
		op: Op,
		*arguments: int,
		extra: bytes = b'',
		name: str | None = None,
	) -> bytes:
		'''
		:return: the data of the response
		:raises J2534Error: the call didn't return NOERROR
		'''
		status, data, text = self._request(function, op, _u32(*arguments) + extra)
		if status != Status.NOERROR:
			raise error_for('{}({})'.format(function, name) if name else function, status, text)
		return data

	def _let_others_go (self) -> None:
		'''
		Wait until threads waiting for the helper got it - Lock isn't fair, a read looping
		over its slices could keep it to itself
		'''
		while self._waiting:
			time.sleep(0.001)

	def _request (self, function: str, op: Op, arguments: bytes) -> tuple[int, bytes, str]:
		'''
		:return: status, data and text of the response
		:raises J2534Error: the helper isn't running
		'''
		with self._waiting_lock:
			self._waiting += 1
		try:
			self._lock.acquire()
		finally:
			with self._waiting_lock:
				self._waiting -= 1
		try:
			process = self._process
			if process is None or process.stdin is None or process.stdout is None:
				raise error_for(function, Status.ERR_FAILED, 'the 32 bit J2534 helper is stopped')
			try:
				process.stdin.write(_u32(op, len(arguments)) + arguments)
				process.stdin.flush()
				status, data_size, text_size = struct.unpack('<3I', _read(process.stdout, 12))
				body = _read(process.stdout, data_size + text_size)
			except (OSError, ValueError, EOFError) as e:
				raise error_for(
					function, Status.ERR_FAILED, 'the 32 bit J2534 helper stopped ({})'.format(
						'exit code {}'.format(process.poll()) if process.poll() is not None else e
					),
				) from e
		finally:
			self._lock.release()
		text = body[data_size:].decode('ascii', errors='replace').strip()
		return status, body[:data_size], text

def _stop (process: subprocess.Popen[bytes]) -> None:
	'''
	Let the helper close what's still open and exit; kill it if it doesn't
	'''
	try:
		if process.stdin is not None:
			process.stdin.close()
	except OSError:
		pass
	try:
		process.wait(STOP_TIMEOUT)
	except subprocess.TimeoutExpired:
		logger.warning('The 32 bit J2534 helper didn\'t exit, killing it')
		process.kill()
		process.wait()
	if process.stdout is not None:
		process.stdout.close()

def _read (stream: IO[bytes], size: int) -> bytes:
	data = stream.read(size)
	if len(data) != size:
		raise EOFError('got {} of {} bytes'.format(len(data), size))
	return bytes(data)

def _u32 (*values: int) -> bytes:
	return struct.pack('<{}I'.format(len(values)), *values)

def _unpack_u32 (data: bytes) -> int:
	return int(U32.unpack_from(data)[0])

def _pack_message (message: PassThruMsg) -> bytes:
	size = min(message.DataSize, MSG_DATA_MAX)
	return MESSAGE_HEADER.pack(
		message.ProtocolID, message.RxStatus, message.TxFlags, message.Timestamp, size,
		message.ExtraDataIndex,
	) + string_at(addressof(message.Data), size)

def _unpack_message (
	data: bytes,
	offset: int,
	message: PassThruMsg | None = None,
) -> tuple[PassThruMsg, int]:
	'''
	:param message: fill this one in instead of a new one
	:return: the message and the offset after it
	'''
	message = message if message is not None else PassThruMsg()
	(
		message.ProtocolID, message.RxStatus, message.TxFlags, message.Timestamp,
		message.DataSize, message.ExtraDataIndex,
	) = MESSAGE_HEADER.unpack_from(data, offset)
	offset += MESSAGE_HEADER.size
	size = min(message.DataSize, MSG_DATA_MAX)
	memmove(message.Data, data[offset:offset + size], size)
	return message, offset + size

def _ioctl_input (data: IoctlData | None) -> bytes:
	if data is None:
		return _u32(Arg.NONE)
	if isinstance(data, SConfigList):
		configs = [data.ConfigPtr[i] for i in range(data.NumOfParams)]
		return _u32(
			Arg.CONFIG_LIST, len(configs), *(x for c in configs for x in (c.Parameter, c.Value)),
		)
	if isinstance(data, PassThruMsg):
		return _u32(Arg.MSG) + _pack_message(data)
	if isinstance(data, SByteArray):
		return _u32(Arg.BYTES, data.NumOfBytes) + string_at(data.BytePtr, data.NumOfBytes)
	return _u32(Arg.ULONG, data.value)

def _ioctl_output (data: IoctlData | None) -> bytes:
	'''
	:raises TypeError: the helper can't fill a config list in
	'''
	if data is None:
		return _u32(Arg.NONE)
	if isinstance(data, PassThruMsg):
		return _u32(Arg.MSG)
	if isinstance(data, SByteArray):
		return _u32(Arg.BYTES, data.NumOfBytes)
	if isinstance(data, c_ulong):
		return _u32(Arg.ULONG)
	raise TypeError('The 32 bit J2534 helper can\'t take a {} from PassThruIoctl'.format(
		type(data).__name__
	))
