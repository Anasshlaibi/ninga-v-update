import hashlib
import struct
import zlib

with open('firmware/original/ATOMNJV.FW', 'rb') as f:
    f.seek(0x10)
    hdr0 = f.read(24)
    pay0 = f.read(1024)
    trailer0 = f.read(4)

expected_crc = 0xe3421d1b

# Check hashes of pay0 (1024 zeros)
for hname in ['md5', 'sha1', 'sha256']:
    h = getattr(hashlib, hname)(pay0).digest()
    for offset in range(len(h) - 3):
        val_le = struct.unpack('<I', h[offset:offset+4])[0]
        val_be = struct.unpack('>I', h[offset:offset+4])[0]
        if val_le == expected_crc or val_be == expected_crc:
            print(f"Match in {hname} of pay0 at offset {offset}!")

# Check hashes of hdr0[:20]
for hname in ['md5', 'sha1', 'sha256']:
    h = getattr(hashlib, hname)(hdr0[:20]).digest()
    for offset in range(len(h) - 3):
        val_le = struct.unpack('<I', h[offset:offset+4])[0]
        val_be = struct.unpack('>I', h[offset:offset+4])[0]
        if val_le == expected_crc or val_be == expected_crc:
            print(f"Match in {hname} of hdr0 at offset {offset}!")

# Check Adler32
print("adler32(pay0):", hex(zlib.adler32(pay0)))
print("adler32(hdr0[:20]):", hex(zlib.adler32(hdr0[:20])))

