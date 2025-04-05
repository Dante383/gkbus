'''
CAN Calibration Protocol example. 
Dump first 512kib of memory to file passed in sys.argv
'''
import inspect
import os
import sys

# dirty hack to import gkbus from this package's source code, not the installed package
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

import argparse
import logging

from gkbus.hardware import CanHardware, TimeoutException
from gkbus.protocol import ccp
from gkbus.transport import CcpOverCanTransport, PacketDirection, RawPacket

SIZE_BYTES = 524290

def packet2hex (packet: RawPacket) -> str:
	direction = 'Incoming' if packet.direction == PacketDirection.INCOMING else 'Outgoing'
	data = ' '.join([hex(x)[2:].zfill(2) for x in packet.data])
	parsed = 'RawPacket({}, ts={}, data={})'.format(direction, packet.timestamp, data)
	return parsed

def test_availability (ccp_client: ccp.CcpProtocol, station_id: int) -> bool:
	try:
		availability = ccp_client.execute(ccp.commands.TestAvailability(station_address=0x01)).get_data()
		return True
	except TimeoutException:
		print('timeout')
	return False
		
def main(args) -> None:
	print('Available CanHardware ports:')
	can_ports = CanHardware.available_ports()
	for port in can_ports:
		print(f'    {port.description()}')

	print('Creating hardware')
	hardware = CanHardware(can_ports[0].port)
	transport = CcpOverCanTransport(hardware, tx_id=0x7e8, rx_id=0x7ea)
	transport.init()

	ccp_client = ccp.CcpProtocol(transport)

	print('\nTesting the availability of station 0x01 at CAN tx_id=0x7e8, rx_id=0x7ea')
	availability = test_availability(ccp_client, 0x01)
	if availability:
		print('positive response')
	else:
		print('timeout. switching to tx_id=0x6a0, rx_id=0x6a1')
		hardware.close()
		transport = CcpOverCanTransport(hardware, tx_id=0x6a0, rx_id=0x6a1)
		transport.init()
		ccp_client.transport = transport
		availability = test_availability(ccp_client, 0x01)
		if not availability:
			print('timeout')
	

	print('\nConnecting to station 0x01')
	resp = ccp_client.execute(ccp.commands.Connect(station_address=0x01))
	print(resp)

	print('\nFetching security seed with resource mask 0x02 (DAQ)')
	seed = ccp_client.execute(ccp.commands.GetSeedForKey(resource_mask=0x02)).get_data()
	print('protection status: {}, seed: {}'.format(seed[0], seed[1:]))
	
	print('\nSending security key (UnlockProtection)')
	ccp_client.execute(ccp.commands.UnlockProtection(key=b'\x44\x45\x45\x54\xC0\x35')).get_data()
	
	base_ptr = 0x60000
	current_ptr = base_ptr
	read_data = bytearray()

	print('\nSetting base memory pointer (MTA0) at 0x0')
	resp = ccp_client.execute(ccp.commands.SetMemoryTransferAddress(mta_number=0x00, address_extension=0x0, address=base_ptr))
	print(resp)

	for x in range(int(SIZE_BYTES/5)):
		print('\nReading 5 bytes @ pointer + 5')
		data = ccp_client.execute(ccp.commands.DataUpload(size=5)).get_data()
		current_ptr += 5
		read_data += data
		print(data)

	print('\nSaving to {}'.format(args.output_filename))
	with open(args.output_filename, 'wb') as f:
		f.write(bytes(read_data))

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('output_filename')
	parser.add_argument('-v', '--verbose', action='count', default=0)
	args = parser.parse_args()

	levels = [logging.WARNING, logging.INFO, logging.DEBUG]
	level = levels[min(args.verbose, len(levels) - 1)]  # cap to last level index
	logging.basicConfig(level=level)

	main(args)