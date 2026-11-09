import struct
import zlib
import os

path = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab/firmware/original/ATOMNJV.FW'
with open(path, 'rb') as f:
    hdr = f.read(16)
    print("Global header:", hdr.hex())
    for i in range(8):
        pos = f.tell()
        s_hdr = f.read(24)
        total_len, magic, ver, sec_id, pay_len, crc = struct.unpack('<I4sIIII', s_hdr)
        print(f"Sec {i} at 0x{pos:x}: total={total_len} (0x{total_len:x}), magic={magic}, ver=0x{ver:08x}, id=0x{sec_id:08x}, pay_len={pay_len}, crc=0x{crc:08x}")
        # skip payload and trailer
        f.seek(pos + total_len)

