import os, sys, inspect

# dirty hack to import gkbus from this package's source code, not the installed package
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from gkbus.hardware import KLineHardware, CanHardware
from gkbus.transport import Kwp2000OverKLineTransport, Kwp2000OverCanTransport
from gkbus.protocol import kwp2000

import logging, argparse

def main():
	print('available KLineHardware ports')
	ports = KLineHardware.available_ports()
	for port in ports:
		print(f'    {port.description()}')

	print('available CanHardware ports')
	can_ports = CanHardware.available_ports()
	for port in can_ports:
		print(f'    {port.description()}')

	print('creating hardware')
	hardware = KLineHardware(ports[0].port)
	hardware.open()

	transport = Kwp2000OverKLineTransport(hardware, tx_id=0x11, rx_id=0xf1)
	kwp = kwp2000.Kwp2000Protocol(transport)
	
	print('fast init')
	init_success = kwp.init(kwp2000.commands.StartCommunication())
	print('fast init : {}'.format(init_success))

	print('executing ReadEcuIdentification: 0x8c - bootloader version')
	response = kwp.execute(kwp2000.commands.ReadEcuIdentification(0x8c))
	print(response)

	bootloader_version = response.get_data()[1:]
	print(' '.join([hex(x) for x in bootloader_version]))
	print(''.join([chr(x) for x in bootloader_version]))

	print('requesting security access seed')
	response = kwp.execute(kwp2000.commands.SecurityAccess().request_seed())
	print(response.get_data())

	print('starting flash reprogramming diagnostic session')
	response = kwp.execute(kwp2000.commands.StartDiagnosticSession(kwp2000.enums.DiagnosticSession.FLASH_REPROGRAMMING))
	print(response)

	print('dumping the buffer')
	packets = transport.buffer_dump()
	print('\n'.join([str(x) for x in packets]))

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-v', '--verbose', action='count', default=0)
	args = parser.parse_args()

	levels = [logging.WARNING, logging.INFO, logging.DEBUG]
	level = levels[min(args.verbose, len(levels) - 1)]  # cap to last level index
	logging.basicConfig(level=level)

main()