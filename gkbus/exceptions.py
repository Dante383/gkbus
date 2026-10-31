'''
Exceptions shared by the device, channel and transport layers
'''

class GkbusException(IOError):
	pass

class ChannelException(GkbusException):
	pass

class OpeningChannelException(ChannelException):
	pass

class TimeoutException(ChannelException):
	pass

class DeviceException(GkbusException):
	pass

class ChannelNotSupportedException(DeviceException):
	pass

class ChannelInUseException(DeviceException):
	pass
