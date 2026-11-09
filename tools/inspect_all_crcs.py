import zlib
import struct

# The 8 sections in ATOMNJV.FW:
# Let's inspect the exact headers:
sections = []
with open('firmware/original/ATOMNJV.FW', 'rb') as f:
    f.seek(16)
    for i in range(8):
        pos = f.tell()
        hdr = f.read(24)
        total_len, magic, ver, sec_id, pay_len, crc = struct.unpack('<I4sIIII', hdr)
        pay = f.read(pay_len)
        trailer = f.read(4)
        sections.append({
            'index': i, 'pos': pos, 'total_len': total_len, 'magic': magic,
            'ver': ver, 'sec_id': sec_id, 'pay_len': pay_len, 'crc': crc,
            'hdr20': hdr[:20], 'trailer': trailer
        })

for s in sections:
    print(f"Sec {s['index']}: id=0x{s['sec_id']:08x}, len={s['pay_len']:9d}, crc=0x{s['crc']:08x}")

