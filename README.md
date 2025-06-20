# GKBus

High level automotive protocol library

```
from gkbus.hardware import CanHardware, KLineHardware
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

print('requesting security access seed')
response = kwp.execute(kwp2000.commands.SecurityAccess().request_seed())
print(response.get_data())

print('starting flash reprogramming diagnostic session')
response = kwp.execute(
	kwp2000.commands.StartDiagnosticSession(
		kwp2000.enums.DiagnosticSession.FLASH_REPROGRAMMING
		)
	)
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

