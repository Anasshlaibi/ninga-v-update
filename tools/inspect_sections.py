import struct

with open('firmware/original/ATOMNJV.FW', 'rb') as f:
    hdr = f.read(16)
    print("Global:", hdr.hex())
    for i in range(8):
        pos = f.tell()
        s_hdr = f.read(24)
        total_len, magic, ver, sec_id, pay_len, crc = struct.unpack('<I4sIIII', s_hdr)
        f.seek(pos + 24 + pay_len)
        trailer = f.read(4)
        print(f"Sec {i} [0x{pos:08x}]: total={total_len:10d}, magic={magic}, ver=0x{ver:08x}, id=0x{sec_id:08x}, pay_len={pay_len:10d}, crc=0x{crc:08x}, trailer=0x{trailer.hex()}")

