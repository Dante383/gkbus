'''
CAN Calibration Protocol example of the Data Acquisition module. 
There are some weird calculations happening in this example 
around the CAN identifier area. This is most likely a SIMK43 quirk and should be ignored
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
from dataclasses import dataclass

from gkbus.hardware import CanFilter, CanHardware
from gkbus.protocol import ccp
from gkbus.transport import CcpOverCanTransport, PacketDirection, RawPacket, TransportABC

CAN_TX_ID = 0x7e8
CAN_RX_ID = 0x7eA

@dataclass
class DaqEntry:
	list_index: int
	available_size: int
	assigned_address: int
	assigned_can_id: int

	def __str__ (self) -> str:
		return 'DaqEntry(i={}, available_size={}, assigned_address={}, assigned_can_id={})'.format(
			hex(self.list_index),
			self.available_size, 
			hex(self.assigned_address), 
			hex(self.assigned_can_id)
		)

	def __repr__ (self) -> str:
		return self.__str__()

def packet2hex (packet: RawPacket) -> str:
	direction = 'Incoming' if packet.direction == PacketDirection.INCOMING else 'Outgoing'
	data = ' '.join([hex(x)[2:].zfill(2) for x in packet.data])
	parsed = 'RawPacket({}, ts={}, data={})'.format(direction, packet.timestamp, data)
	return parsed

def dump_buffer (transport: TransportABC) -> None:
	print('\nDumping the buffer')
	packets = transport.buffer_dump()
	print('\n'.join([packet2hex(x) for x in packets]))

def main():
	print('Available CanHardware ports:')
	can_ports = CanHardware.available_ports()
	for port in can_ports:
		print(f'    {port.description()}')

	print('Creating hardware with tx_id={}, rx_id={}'.format(hex(CAN_TX_ID), hex(CAN_RX_ID)))
	hardware = CanHardware(can_ports[0].port)
	transport = CcpOverCanTransport(hardware, tx_id=CAN_TX_ID, rx_id=CAN_RX_ID)
	transport.init()
	
	ccp_client = ccp.CcpProtocol(transport)

	print('\nConnecting to station 0x01')
	ccp_client.execute(ccp.commands.Connect(station_address=0x01))

	print('\nFetching security seed with resource mask DAQ=1')
	ccp_client.execute(ccp.commands.GetSeedForKey(resource_mask=ccp.types.ResourceMaskBitfield(DAQ=1)))
	
	print('\nSending security key (UnlockProtection)')
	ccp_client.execute(ccp.commands.UnlockProtection(key=b'\x44\x45\x45\x54\xC0\x35'))

	daq_entries = []

	print('\nRequesting sizes of DAQ lists #30-40, which will also clear them')
	print('This is also, weirdly, the point where we need to assign CAN IDs for our DAQ entries')
	print('I\'ll assign 0x7D0+x, x being the DAQ list index')
	print('DAQ lists, with size=0 ones skipped:')
	
	for index in range(0,60):
		can_identifier = 0x07D0+index
		address = 0xF574-(index*2)

		daq_size = ccp_client.execute(ccp.commands.GetSizeOfDaqList(list_number=index, can_identifier=can_identifier)).get_data()

		daq_list_size = daq_size[0]
		daq_first_pid = daq_size[1]

		if daq_list_size <= 0:
			continue
		
		print('DAQ index: {}, size: {}, first pid: {}'.format(index, daq_list_size, daq_first_pid))
		daq_entries.append(
			DaqEntry(
				list_index=index, 
				available_size=daq_list_size, 
				assigned_address=address,
				assigned_can_id=can_identifier-0x02 # why 0x02? i have no idea
			)
		)
		ccp_client.execute(ccp.commands.SetDaqListPointer(list_number=index, odt_number=0x0, element_number=0)).get_data()
		
		print('    assigning data source address: {}'.format(hex(address)))
		ccp_client.execute(ccp.commands.WriteDaqListEntry(size=0x02, address_extension=0x0, address=address)).get_data()

	if len(daq_entries) == 0:
		print('No usable DAQ lists found! Perhaps the ECU is poorly implemented and doesn\'t support DAQ?')
		return dump_buffer(transport)

	# intuition is suggesting that this should be done in the loop above, 
	# but this is the way a certain OEM tool did it - first set every DAQ up,
	# only then flip them all to PREPARE
	print('\n{} non-zero length lists found. A memory address was assigned to each of them. Now, we\'ll flip them all to Ready To Transmit state'.format(len(daq_entries)))
	for daq_entry in daq_entries:
		ccp_client.execute(
			ccp.commands.StartStopDataTransmission(
				mode=ccp.enums.DataTransmissionMode.PREPARE, 
				daq_list_number=daq_entry.list_index, 
				last_odt_number=0x0, 
				event_channel=daq_entry.list_index,
				prescaler=0x0001
			)
		).get_data()

	print('\nAll DAQs are now ready to transmit. Starting synchronised data transmission')
	ccp_client.execute(ccp.commands.StartStopSynchronisedDataTransmission(ccp.enums.DataTransmissionRequest.START))

	print('\nSwitching CCP session status to DAQ=1, STORE=1')
	ccp_client.execute(ccp.commands.SetSessionStatus(
		int.from_bytes(
			ccp.types.SessionStatusBitfield(DAQ=1, STORE=1),
			'little'
		)
	))

	
	print('\nRestarting the CAN interface to include DAQ identifiers in the rx filter')
	hardware.close()
	
	# this is a really dirty way of doing that, using private properties 
	# that might change at any time. not recommended. @todo add proper filter api to CAN hardware
	can_filters = [CanFilter(can_id=CAN_RX_ID, can_mask=0x7ff)]
	print('\nActive DAQ entries:')
	for entry in daq_entries:
		can_filters.append(CanFilter(can_id=entry.assigned_can_id, can_mask=0x7ff))
		print(entry)
	hardware.set_filters(can_filters)
	transport.init()

	print('\nFetching DAQ entries value until CTRL+C')

	daq_entries_len = len(daq_entries)
	entry_values = {} # key = can identifier

	print('')

	try:
		while True:
			frame = hardware.read(length=8)
			entry_values[frame.identifier] = frame.data
			
			formatted = ''
			for k, v in entry_values.items():
				formatted += ('{}: {}, '.format(hex(k), ' '.join([hex(x)[2:].zfill(2) for x in list(v)])))
			print(formatted[:-2], end='\r')
	except KeyboardInterrupt:
		pass
	
	dump_buffer(transport)

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-v', '--verbose', action='count', default=0)
	args = parser.parse_args()

	levels = [logging.WARNING, logging.INFO, logging.DEBUG]
	level = levels[min(args.verbose, len(levels) - 1)]  # cap to last level index
	logging.basicConfig(level=level)

	main()