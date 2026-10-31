import inspect
import os
import sys

# dirty hack to import gkbus from this package's source code, not the installed package
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

import argparse
import logging

from gkbus.device import J2534Device, ObdPin
from gkbus.device.j2534 import find_libraries
from gkbus.protocol import kwp2000
from gkbus.transport import Kwp2000OverCanTransport, Kwp2000OverKLineTransport, TransportABC


def main(library: str | None, bus: str, pin: int, ground: list[int]) -> None:
	print('installed J2534 libraries')
	for info in find_libraries():
		print(f'    {info.name} ({info.vendor}): {info.path}')

	# J2534Device(None) takes the first installed library, 'openport' the first one matching it
	with J2534Device(library) as device:
		print(device.description())
		print(f'    library {device.library_version}, API {device.api_version}')
		print(f'    battery {device.battery_voltage():.2f} V')
		print(f'    K-Line on pins {sorted(int(x) for x in device.kline_pins())}')
		print(f'    can ground pins {sorted(int(x) for x in device.groundable_pins())}')

		# pins the adapter can't ground are logged as a warning for the user to wire up instead.
		# Closing the device releases them all, too
		with device.grounded(*[ObdPin(x) for x in ground]):
			transport: TransportABC
			if bus == 'kline':
				transport = Kwp2000OverKLineTransport(
					device.kline(pin=ObdPin(pin)), tx_id=0x11, rx_id=0xf1,
				)
			else:
				transport = Kwp2000OverCanTransport(device.canbus(), tx_id=0x7E0, rx_id=0x7E8)
			kwp = kwp2000.Kwp2000Protocol(transport)

			if bus == 'kline':
				print('fast init')
				print('fast init : {}'.format(kwp.init(kwp2000.commands.StartCommunication())))

			print('executing ReadEcuIdentification: 0x8c - bootloader version')
			response = kwp.execute(kwp2000.commands.ReadEcuIdentification(0x8c))
			print(response)
			print(''.join([chr(x) for x in response.get_data()[1:]]))

			kwp.close()

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-v', '--verbose', action='count', default=0)
	parser.add_argument(
		'-l', '--library', help='part of a J2534 library name (e.g. openport) or its path',
	)
	parser.add_argument('-b', '--bus', choices=['kline', 'canbus'], default='kline')
	parser.add_argument('-p', '--pin', type=int, default=7, help='OBD pin to do K-Line on')
	parser.add_argument(
		'-g', '--ground', type=int, nargs='*', default=[], help='OBD pins to ground meanwhile',
	)
	args = parser.parse_args()

	levels = [logging.WARNING, logging.INFO, logging.DEBUG]
	level = levels[min(args.verbose, len(levels) - 1)]  # cap to last level index
	logging.basicConfig(level=level)

	main(args.library, args.bus, args.pin, args.ground)
