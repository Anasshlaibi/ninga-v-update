import zlib
import struct

with open('firmware/original/ATOMNJV.FW', 'rb') as f:
    for i in [0, 1, 2, 6]:
        f.seek([0x10, 0x42c, 0x848, 0x130c0cb8][[0, 1, 2, 6].index(i)])
        hdr = f.read(24)
        total_len, magic, ver, sec_id, pay_len, expected_crc = struct.unpack('<I4sIIII', hdr)
        pay = f.read(pay_len)
        trailer = f.read(4)
        
        # test header[:20]
        # test header[:20] + pay
        # test header[:16]
        # test ver + sec_id + pay_len
        print(f"Sec {i} expected_crc: {hex(expected_crc)}")
        print(f"  crc32(hdr[:20]): {hex(zlib.crc32(hdr[:20]))}")
        print(f"  crc32(hdr[:16]): {hex(zlib.crc32(hdr[:16]))}")
        print(f"  crc32(hdr[:20]+pay): {hex(zlib.crc32(hdr[:20]+pay))}")
        print(f"  crc32(hdr[:20]+pay+trailer): {hex(zlib.crc32(hdr[:20]+pay+trailer))}")
        print(f"  crc32(pay+hdr[:20]): {hex(zlib.crc32(pay+hdr[:20]))}")

