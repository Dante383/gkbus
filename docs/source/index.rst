GKBus
===================================

Automotive diagnostic protocols library powering the `GKFlasher <https://github.com/dante383/GKFlasher>`_

.. code-block:: python
    :linenos:

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

    print('executing ReadEcuIdentification: 0x8c - bootloader version')
    response = kwp.execute(kwp2000.commands.ReadEcuIdentification(0x8c))
    print(response)

    kwp.close()


Supported protocols
====================

- Kwp2000 (ISO14230) - over CAN and K-Line

- CCP (Can Calibration Protocol) - over CAN

Supported hardware
====================

.. list-table::
    :widths: 30, 70
    :header-rows: 1

    * - Physical layer
      - Supported hardware
    * - K-Line (ISO 9141-2/14230-1)
      - Basically any native serial port. Genuine FTDI adapters work best, knockoff FTDI and CH340 are also tested
    * - CAN bus
      - On Linux, anything that shows up as a SocketCAN network interface, using the kernel ISO-TP module. On Windows, PCAN, Vector, slcan and GS-USB (CANable) adapters through python-can. Other python-can interfaces can be used with ``find_device('interface:channel')``

Installing
==========

GKBus is available on PyPI:

.. code-block:: console

    $ python -m pip install gkbus

Overview
=========

GKBus operates on these layers:

- Device - the physical adapter. Find them with ``discover()``, or create one from a port name with ``find_device()``
- Channel - one bus on a device, ``device.kline()`` or ``device.canbus()``. Reads and writes bytes (K-Line) or frames (CAN)
- Transport - turns protocol PDUs into what goes over the channel (K-Line framing, ISO-TP). Opens the channel if it isn't open yet and then closes it too - a channel you opened yourself stays open
- Protocol - KWP2000, CCP

.. toctree::
    :maxdepth: 2
    :caption: API reference

    api/device
    api/channel
    api/transport
    api/protocol
    api/exceptions

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
