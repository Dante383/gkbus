GKBus
===================================

Automotive diagnostic protocols library powering the `GKFlasher <https://github.com/dante383/GKFlasher>`_

.. code-block:: python
    :linenos:

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

    print('executing ReadEcuIdentification: 0x8c - bootloader version')
    response = kwp.execute(kwp2000.commands.ReadEcuIdentification(0x8c))
    print(response)


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
      - On Linux, anything that shows up as a native CAN network interface. Kernel ISO-TP module is used when available. On Windows, while everything supported by python-can should work, it was not tested. 

Installing 
===========

GKBus is available on PyPi:

```console
$ python -m pip install gkbus
```

API Reference available on [Read the Docs](https://gkbus.readthedocs.io)
========================================================================

.. automodule:: gkbus.hardware
    :members:
    :imported-members:

.. automodule:: gkbus.transport
    :members:
    :imported-members:

.. automodule:: gkbus.protocol
    :members:
    :imported-members: 

Overview
=========

GKBus operates on three layers: hardware, transport, protocol.
[...]

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
