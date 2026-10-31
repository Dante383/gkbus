# GKBus

High level automotive protocol library

```
from gkbus.device import Bus, discover
from gkbus.protocol import kwp2000
from gkbus.transport import Kwp2000OverKLineTransport

print('available devices')
for device in discover():
	print(f'    {device.description()}')

device = discover({Bus.KLINE})[0] # or find_device('/dev/ttyUSB0')
channel = device.kline() # for CAN: device.canbus() and Kwp2000OverCanTransport
transport = Kwp2000OverKLineTransport(channel, tx_id=0x11, rx_id=0xf1)
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

kwp.close()
```

## Layers

- **Device** - the physical adapter (KKL cable, SocketCAN interface, PCAN, ...). Find them with
  `discover()`, or create one from a port name with `find_device()`
- **Channel** - one bus on a device, `device.kline()` or `device.canbus()`. Reads and writes
  bytes (K-Line) or frames (CAN)
- **Transport** - turns protocol PDUs into what goes over the channel (K-Line framing, ISO-TP).
  Opens the channel if it isn't open yet and then closes it too - a channel you opened yourself
  stays open, so you can hand it from one transport to the next
- **Protocol** - KWP2000, CCP

## Supported protocols

- Kwp2000 (ISO14230) - over CAN and K-Line

- CCP (Can Calibration Protocol)

## Installing 

GKBus is available on PyPi:

```console
$ python -m pip install gkbus
```

## API Reference available on [Read the Docs](https://gkbus.readthedocs.io)

