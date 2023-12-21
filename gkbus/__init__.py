import importlib

protocols = {
	'canbus': ('gkbus.interface.CanInterface', 'CanInterface'),
	'kline': ('gkbus.interface.KLineInterface', 'KLineInterface')
}

def Bus (protocol: str, interface: str, **kwargs):
	try:
		module_name, class_name = protocols[protocol]
	except KeyError:
		raise Exception('Protocol %s not implemented', protocol)

	module = importlib.import_module(module_name)
	bus_class = getattr(module, class_name)

	bus = bus_class(interface=interface, **kwargs)

	return bus

class GKBusTimeoutException (Exception):
	pass