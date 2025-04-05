# GKBus

Automotive diagnostic protocols library powering the [GKFlasher](https://github.com/dante383/GKFlasher)

```from gkbus.hardware import CanHardware, KLineHardware
from gkbus.protocol import kwp2000
from gkbus.transport import Kwp2000OverKLineTransport

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
transport = Kwp2000OverKLineTransport(hardware, tx_id=0x11, rx_id=0xf1)
kwp = kwp2000.Kwp2000Protocol(transport)
	
print('fast init')
init_success = kwp.init(kwp2000.commands.StartCommunication())
print('fast init : {}'.format(init_success))

print('executing ReadEcuIdentification: 0x8c - bootloader version')
response = kwp.execute(kwp2000.commands.ReadEcuIdentification(0x8c))
print(response)
```

## Supported protocols

- Kwp2000 (ISO14230) - over CAN and K-Line

- CCP (Can Calibration Protocol)

## Installing 

GKBus is available on PyPi:

```console
$ python -m pip install gkbus
```

## API Reference available on [Read the Docs](https://gkbus.readthedocs.io)

