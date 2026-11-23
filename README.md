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

- **Device** - the physical adapter (KKL cable, SocketCAN interface, PCAN, J2534, ...). Find them with
  `discover()`, or create one from a port name with `find_device()`
- **Channel** - one bus on a device, `device.kline()` or `device.canbus()`. Reads and writes
  bytes (K-Line) or frames (CAN)
- **Transport** - turns protocol PDUs into what goes over the channel (K-Line framing, ISO-TP).
  Opens the channel if it isn't open yet and then closes it too - a channel you opened yourself
  stays open, so you can hand it from one transport to the next
- **Protocol** - KWP2000, CCP

## Devices

Code written against a channel doesn't care which adapter is behind it.

| Device | Buses | Port string |
|---|---|---|
| Serial K-Line (KKL / FTDI cable) | K-Line | `/dev/ttyUSB0`, `COM3` |
| SocketCAN (Linux) | CAN | `can0` |
| python-can (PCAN, Kvaser, ...) | CAN | `pcan:PCAN_USBBUS1` |
| J2534 PassThru (OpenPort 2.0, ...) | K-Line, CAN | `j2534`, `j2534:openport`, `j2534:/path/to/lib.so` |

### J2534

gkbus ships [openport-j2534](https://github.com/bisak/openport-j2534), an open source driver
for the Tactrix OpenPort 2.0, and uses it on every platform - there is no driver to install
for an OpenPort:

- **Linux** (x86_64): needs libusb-1.0 (`libusb-1.0-0` on Debian / Ubuntu, usually there
  already) and a udev rule so your user can open the cable, then re-plug it:
  `echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="cc4d", MODE="0666"' | sudo tee /etc/udev/rules.d/70-openport.rules`
- **Windows** (32 and 64 bit Python): the cable works with Tactrix's USB driver if it's
  installed, and with the USB serial driver Windows 10 and later give it otherwise
- **macOS**, other Linux architectures: no build is shipped yet, install openport-j2534
  yourself. gkbus finds `libj2534.so` / `libj2534.dylib` in the usual places
- Remove the cable's microSD card, with one inserted it shows up as a USB disk
- Other adapters need their vendor's J2534 library: registered in the Windows registry
  (it has to match the bitness of your Python) or in `~/.passthru/*.json`
- `j2534` is the first library found: `GKBUS_J2534_LIBRARY`, then the shipped openport-j2534,
  then installed ones. Installed OpenPort drivers (Tactrix's DLL, another openport-j2534)
  aren't listed next to the shipped one; to use one anyway, point `GKBUS_J2534_LIBRARY` at
  it or use `j2534:/path/to/library`
- `OPENPORT_LOG=/tmp/openport.log` logs openport-j2534's USB traffic
- Freezing an app with PyInstaller: gkbus' hook bundles the drivers, nothing to add to the
  spec
- To update the shipped drivers, run `gkbus/device/j2534/drivers/build.sh` with an
  openport-j2534 checkout, a release tag and the release's Windows zip, e.g.
  `build.sh ../openport-j2534 v0.5.0 openport-j2534-v0.5.0-windows.zip`. The Linux library
  is built from the tag (needs libusb's headers), the DLLs are the release's own.
  `gkbus/device/j2534/drivers/VERSION` says what is shipped; openport-j2534 is GPL-3.0-or-later
  like gkbus, its `LICENSE` and `NOTICE` are next to it
- ISO-TP is done by the adapter. The OpenPort pads frames with `0x00`, not `0xCC`
- K-Line timing (P1, P3, P4) is kept by the adapter, see `KLineTiming`. Fast baudrates work
  with exact values, e.g. the SIMK43's 19231, 39474, 57692 and 125000 (24 MHz / 16 / {78, 38,
  26, 12})

### Serial K-Line

- The serial channel honors P3_MIN (the pause before each request) from `KLineTiming` and
  sends request bytes back to back. The 60 ms default is safe for the SIMK43 in the default
  session; after negotiating shorter timing with `AccessTimingParameters`, call
  `channel.set_timing(KLineTiming(p3_min=...))` to speed bulk reads up. Keep a margin floor:
  the SIMK43 advertises p3min=0 but drops requests that arrive too soon after its response
  (measured on the bench: 7 ms fails, 10 ms works), so ~20 ms gives ~2x headroom. At 125000
  baud a ~20 ms floor cuts a full 254-byte read from ~140 ms to ~50 ms (~10 ms reaches ~40 ms
  but with little margin) on an FTDI cable
- Negotiated timing only lasts until the next `StartDiagnosticSession`: the ECU drops back to
  its defaults then (the SIMK43 ignores requests sent sooner than ~55 ms after its response
  again, even if the new session is the same). `Kwp2000Protocol` follows it and resets the
  channel to the timing it was created with (`KLineChannel.reset_timing()`) before sending
  one, on serial and J2534 alike. Renegotiate and call `set_timing()` again to stay fast
- FTDI adapters buffer for 16 ms by default (the latency timer). gkbus drops it to 1 ms while
  the port is open - no privileges needed on Linux, and it's restored on close. On Windows,
  lower it by hand in Device Manager - the adapter's COM port - Advanced - Latency Timer, or
  it caps throughput

### OBD pins

J2534 adapters can do K-Line on other OBD pins and ground pins. Other devices log what
to wire by hand instead, so the same code works with any adapter:

```
from gkbus.device import ObdPin

channel = device.kline(pin=ObdPin.L_LINE)  # K-Line on pin 15
print(device.kline_pins(), device.groundable_pins())

# grounded while inside, released afterwards. Returns the pins to ground by hand
with device.grounded(ObdPin.PIN_9, ObdPin.PIN_12) as manual:
	...
```

`device.ground_pin()` / `device.release_pin()` do the same without the context manager, and
`device.close()` releases whatever is still grounded. Some OpenPort 2.0 clones acknowledge
grounding pins 1, 3, 9, 11, 12 and 13 but don't do it, check with a multimeter.

## Supported protocols

- Kwp2000 (ISO14230) - over CAN and K-Line

- CCP (Can Calibration Protocol)

## Installing 

GKBus is available on PyPi:

```console
$ python -m pip install gkbus
```

## API Reference available on [Read the Docs](https://gkbus.readthedocs.io)

