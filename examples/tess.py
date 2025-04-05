import ctypes

# Define a bitfield in a single byte, using LittleEndianStructure for clarity
class MyBitField(ctypes.LittleEndianStructure):
    _fields_ = [
        ("bit0", ctypes.c_uint8, 1),
        ("bit1", ctypes.c_uint8, 1),
        ("bit2", ctypes.c_uint8, 1),
        ("bit3", ctypes.c_uint8, 1),
        ("bit4", ctypes.c_uint8, 1),
        ("bit5", ctypes.c_uint8, 1),
        ("bit6", ctypes.c_uint8, 1),
        ("bit7", ctypes.c_uint8, 1),
    ]

bf = MyBitField()

# Pick bits to set; here we'll set bit1 and bit6 to get 0x42 in hex (binary 01000010)
bf.bit1 = 1
bf.bit6 = 1

# Check Python's idea of the structure's size
print("Size of MyBitField:", ctypes.sizeof(bf))  # Should be 1

# Convert to bytes
raw_bytes = ctypes.string_at(ctypes.byref(bf), ctypes.sizeof(bf))
print("Bytes (hex):", raw_bytes.hex())
# On a typical little‐endian system, this should print '42'
