'''
CAN Calibration Protocol example, featuring searching for 
a station on 2 different CAN IDs, interpreting all available
information and reading from both base pointer (MTA) location
and specified address with extension
'''
import os, sys, inspect

# dirty hack to import gkbus from this package's source code, not the installed package
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from gkbus.hardware import CanHardware, TimeoutException
from gkbus.transport import CcpOverCanTransport, RawPacket, PacketDirection
from gkbus.protocol import ccp

import logging, argparse

def packet2hex (packet: RawPacket) -> str:
	direction = 'Incoming' if packet.direction == PacketDirection.INCOMING else 'Outgoing'
	data = ' '.join([hex(x)[2:].zfill(2) for x in packet.data])
	parsed = 'RawPacket({}, ts={}, data={})'.format(direction, packet.timestamp, data)
	return parsed

def status_bit_to_str (bit: str) -> str:
	return '{} ({})'.format(bit, 'Available' if bit == '1' else 'Unavailable')

def unpack_resource_mask (mask: int) -> dict: 
	bits = bin(mask)[2:].zfill(8)

	return {
		'CAL': status_bit_to_str(bits[0]),
		'DAQ': status_bit_to_str(bits[1]),
		'reserved': status_bit_to_str(bits[2]),
		'reserved': status_bit_to_str(bits[3]),
		'reserved': status_bit_to_str(bits[4]),
		'reserved': status_bit_to_str(bits[5]),
		'PGM (memory programming)': status_bit_to_str(bits[6]),
		'reserved': status_bit_to_str(bits[7])
	}

def test_availability (ccp_client: ccp.CcpProtocol, station_id: int) -> bool:
	try:
		availability = ccp_client.execute(ccp.commands.TestAvailability(station_address=0x01)).get_data()
		return True
	except TimeoutException:
		print('timeout')
	return False
		
def main():
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
	resp = ccp_client.execute(ccp.commands.UnlockProtection(key=b'\x44\x45\x45\x54\xC0\x35')).get_data()
	print('current privilege status resource mask: {}'.format(hex(resp[0])))
	privilege_status = unpack_resource_mask(resp[1])
	print('current privilege status:')
	for k, v in privilege_status.items():
		print('    {}: {}'.format(k, v))
	

	print('\nGetting the CCP version')
	version = ccp_client.execute(
		ccp.commands.GetImplementedVersionOfCcp(
			main_protocol_version=0x02, 
			release_protocol_version=0x01
			)
		).get_data()
	main_version = version[0]
	release = version[1]
	print('v{}.{}'.format(main_version, release))

	print('\nExchanging station identifications')
	station_ids = ccp_client.execute(ccp.commands.ExchangeStationIdentifications()).get_data()
	slave_id_length = station_ids[0]
	slave_data_type_qualifier = station_ids[1]
	resource_availability_mask = station_ids[2]
	resource_protection_mask = station_ids[3]
	print('slave id length: {}, slave data type qualifier: {}, resource availability mask: {}, resource protection mask: {}'.format(
		hex(slave_id_length), hex(slave_data_type_qualifier), hex(resource_availability_mask), hex(resource_protection_mask)
	))
	resource_availability = unpack_resource_mask(resource_availability_mask)
	print('resource availability:')
	for k, v in resource_availability.items():
		print('    {}: {}'.format(k, v))

	resource_protection = unpack_resource_mask(resource_protection_mask)
	print('resource protection:')
	for k, v in resource_protection.items():
		print('    {}: {}'.format(k, v))

	print('\nGetting currently active calibration page')
	page = ccp_client.execute(ccp.commands.GetCurrentlyActiveCalibrationPage()).get_data()
	print('addr extension: {}, addr: {}'.format(hex(page[0]), hex(int.from_bytes(page[1:], 'little'))))

	# cannot test: simk43 ca663056 returns 0x32 params out of range for size=0x100, 0x33 access denied for size=0x10
	#print('\nBuilding a checksum from 0x1000 bytes starting at MTA0')
	#checksum = ccp_client.execute(ccp.commands.BuildChecksum(size=0x10)).get_data()
	#print(checksum)

	print('\nGetting session status')
	status = ccp_client.execute(ccp.commands.GetSessionStatus()).get_data()
	print('status: {}, additional status info qualifier: {}, additional status info: {}'.format(
		status[0], status[1], status[2:]
	))

	# lets not execute anything invasive in the example
	#print('\nGetting the size of DAQ list #0, which will also clear it')
	#daq_size = ccp_client.execute(ccp.commands.GetSizeOfDaqList(list_number=0)).get_data()
	#daq_list_size = daq_size[0]
	#daq_first_pid = daq_size[1]
	#print('size: {}, first pid: {}'.format(daq_list_size, daq_first_pid))

	print('\nSetting base memory pointer (MTA0) at 0x90000')
	resp = ccp_client.execute(ccp.commands.SetMemoryTransferAddress(mta_number=0x00, address_extension=0x0, address=0x90000))
	print(resp)

	print('\nReading 5 bytes @ base pointer')
	data = ccp_client.execute(ccp.commands.DataUpload(size=5)).get_data()
	print(data)

	print('\nReading 5 bytes @ base pointer + 5')
	data = ccp_client.execute(ccp.commands.DataUpload(size=5)).get_data()
	print(data)

	print('\nReading 4 bytes at 0x3E01')
	data = ccp_client.execute(ccp.commands.ShortUpload(size=4, address_extension=0, address=0x3E01)).get_data()
	print(data)

	print('\nDumping the buffer')
	packets = transport.buffer_dump()
	print('\n'.join([packet2hex(x) for x in packets]))

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-v', '--verbose', action='count', default=0)
	args = parser.parse_args()

	levels = [logging.WARNING, logging.INFO, logging.DEBUG]
	level = levels[min(args.verbose, len(levels) - 1)]  # cap to last level index
	logging.basicConfig(level=level)

	main()