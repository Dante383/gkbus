from enum import IntEnum


class ObdPin(IntEnum):
	'''
	Pin of the SAE J1962 (OBD-II) connector. ObdPin(7) works too, e.g. for pins read from
	a config file
	'''
	PIN_1 = 1
	PIN_2 = 2
	PIN_3 = 3
	PIN_4 = 4
	PIN_5 = 5
	PIN_6 = 6
	PIN_7 = 7
	PIN_8 = 8
	PIN_9 = 9
	PIN_10 = 10
	PIN_11 = 11
	PIN_12 = 12
	PIN_13 = 13
	PIN_14 = 14
	PIN_15 = 15
	PIN_16 = 16

	CHASSIS_GROUND = 4
	SIGNAL_GROUND = 5
	CAN_HIGH = 6
	K_LINE = 7
	CAN_LOW = 14
	L_LINE = 15
	BATTERY = 16

	def __str__ (self) -> str:
		return 'OBD pin {}'.format(self.value)

#: pins that are ground or battery - nothing can be switched onto them
POWER_PINS = frozenset({ObdPin.CHASSIS_GROUND, ObdPin.SIGNAL_GROUND, ObdPin.BATTERY})
