'''
GKBus: High level automotive protocol library
'''

from .exceptions import (
	ChannelException,
	ChannelInUseException,
	ChannelNotSupportedException,
	DeviceException,
	GkbusException,
	OpeningChannelException,
	TimeoutException,
)

__version__ = '0.5.0'

__all__ = [
	'ChannelException',
	'ChannelInUseException',
	'ChannelNotSupportedException',
	'DeviceException',
	'GkbusException',
	'OpeningChannelException',
	'TimeoutException',
	'__version__',
]
