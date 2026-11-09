import zlib
import struct

with open('firmware/original/ATOMNJV.FW', 'rb') as f:
    f.seek(0x10)
    # Sec 0: header is 24 bytes
    s0_hdr = f.read(24)
    # payload is 1024 bytes
    s0_pay = f.read(1024)
    expected_crc = struct.unpack('<I', s0_hdr[20:24])[0]

print("Expected CRC:", hex(expected_crc))

# Test different CRC32 variants on payload
def crc32_mpeg2(data):
    # polynomial 0x04C11DB7
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= (b << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc

def crc32_posix(data):
    return ~crc32_mpeg2(data) & 0xFFFFFFFF

print("zlib.crc32(payload):", hex(zlib.crc32(s0_pay)))
print("crc32_mpeg2(payload):", hex(crc32_mpeg2(s0_pay)))
print("crc32_posix(payload):", hex(crc32_posix(s0_pay)))

