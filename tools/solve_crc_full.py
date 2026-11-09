import struct
import zlib

# We have 8 sections with known inputs and known CRCs:
# Sec 0: id=0xaaaaaaaa, len=1024 (zeros), crc=0xe3421d1b
# Sec 1: id=0xaaaaaaab, len=1024 (zeros), crc=0x9d9abe5f
# Sec 2: id=0xaaaaaaa2, len=1024 (zeros), crc=0xa3650bb9
# Sec 6: id=0xaaaaaaa1, len=1024 (zeros), crc=0x200cee75

# Notice Sec 0, 1, 2, 6 all have identical 1024 zeros payload.
# If the CRC was ONLY over the payload, all 4 would have the same CRC!
# But their CRCs are DIFFERENT!
# Therefore, the CRC MUST INCLUDE THE HEADER (or at least the section_id)!

# Let's test what parts of the header are passed into the CRC function:
# Header is 24 bytes:
# [0:4] total_len
# [4:8] magic
# [8:12] version
# [12:16] sec_id
# [16:20] pay_len
# [20:24] crc

# Let's test standard CRC-32 (poly 0x04C11DB7) with various initial values and xorout:
poly = 0x04C11DB7

def calc_crc(data, init, xorout):
    crc = init
    for b in data:
        crc ^= (b << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ poly) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc ^ xorout

# Candidate header buffers for Sec 0 (id 0xaaaaaaaa):
candidates = [
    ("hdr20", struct.pack('<I4sIII', 1052, b' nib', 0x01000000, 0xaaaaaaaa, 1024)),
    ("hdr20_be", struct.pack('>I4sIII', 1052, b'bin ', 0x01000000, 0xaaaaaaaa, 1024)),
    ("ver_id_len", struct.pack('<III', 0x01000000, 0xaaaaaaaa, 1024)),
    ("id_only", struct.pack('<I', 0xaaaaaaaa)),
    ("hdr16", struct.pack('<I4sII', 1052, b' nib', 0x01000000, 0xaaaaaaaa)),
    ("hdr20_plus_pay", struct.pack('<I4sIII', 1052, b' nib', 0x01000000, 0xaaaaaaaa, 1024) + b'\x00' * 1024),
]

target0 = 0xe3421d1b
target1 = 0x9d9abe5f

found = False
for name, buf in candidates:
    # We can solve for init and xorout using two known targets!
    # Let's construct buf1 for Sec 1:
    buf1 = buf.replace(b'\xaa\xaa\xaa\xaa', b'\xab\xaa\xaa\xaa')
    
    # In a linear CRC:
    # CRC(x) = L(x) ^ (init_term) ^ xorout
    # Delta CRC = CRC(buf0) ^ CRC(buf1) = L(buf0 ^ buf1)
    d_actual = target0 ^ target1
    d_calc = calc_crc(bytes(a ^ b for a, b in zip(buf, buf1)), 0, 0)
    if d_calc == d_actual:
        print(f"MATCH on delta for candidate: {name}!")
        # Now find init and xorout
        for init in [0, 0xFFFFFFFF]:
            xorout = calc_crc(buf, init, 0) ^ target0
            if calc_crc(buf1, init, xorout) == target1:
                print(f"  FOUND! init={hex(init)}, xorout={hex(xorout)}")
                found = True

if not found:
    print("No direct match among standard header candidates.")

