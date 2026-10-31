class DeviceException(IOError):
	pass

class DeviceNotOpenException(DeviceException):
	pass

class ChannelNotSupportedException(DeviceException):
	pass

class ChannelInUseException(DeviceException):
	pass
