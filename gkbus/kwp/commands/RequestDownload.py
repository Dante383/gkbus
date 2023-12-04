from ..KWPCommand import KWPCommand

class RequestDownload(KWPCommand):
	command = 0x34
	offset = 0x0
	size = 0

	def __init__ (self, offset, size):
		self.offset = offset 
		self.size = size 

		offset_b1 = (self.offset >> 16) & 0xFF
		offset_b2 = (self.offset >> 8) & 0xFF
		offset_b3 = self.offset & 0xFF

		data_format = 0x00 # uncompressed, unencrypted

		size_b1 = (self.size >> 16) & 0xFF
		size_b2 = (self.size >> 8) & 0xFF
		size_b3 = self.size & 0xFF

		self.data = [offset_b1, offset_b2, offset_b3, data_format, size_b1, size_b2, size_b3]