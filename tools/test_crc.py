import struct
import zlib
import binascii

path = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab/firmware/original/ATOMNJV.FW'
with open(path, 'rb') as f:
    hdr = f.read(16)
    pos = f.tell()
    s_hdr = f.read(24)
    total_len, magic, ver, sec_id, pay_len, expected_crc = struct.unpack('<I4sIIII', s_hdr)
    pay = f.read(pay_len)
    trailer = f.read(4)

    print("Header bytes (20 bytes before crc):", s_hdr[:20].hex())
    print("Expected CRC:", hex(expected_crc))

    # Check various CRCs on the 20 header bytes
    c_hdr = zlib.crc32(s_hdr[:20])
    print("CRC32(header[:20]):", hex(c_hdr))

    # Check CRC on payload
    c_pay = zlib.crc32(pay)
    print("CRC32(payload):", hex(c_pay))

    # Check CRC on header[:20] + payload
    c_all = zlib.crc32(s_hdr[:20] + pay)
    print("CRC32(header[:20] + payload):", hex(c_all))

