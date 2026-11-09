import struct

# Let's test Sec 0:
# total_len = 1052 = 0x41c
# magic = b' nib'
# ver = 0x01000000
# sec_id = 0xaaaaaaaa
# pay_len = 1024 = 0x400
# expected = 0xe3421d1b

# We know the input to the checksum is either:
# Case A: The 20 bytes of header: 1c040000206e696200000001aaaaaaaa00040000
# Case B: The 1024 zero bytes of payload
# Case C: 20 bytes header + 1024 bytes payload
# Case D: Just (ver, sec_id, pay_len)
# Case E: Just sec_id

inputs = {
    'hdr20': struct.pack('<I4sIII', 1052, b' nib', 0x01000000, 0xaaaaaaaa, 1024),
    'pay1024': b'\x00' * 1024,
    'hdr20_pay': struct.pack('<I4sIII', 1052, b' nib', 0x01000000, 0xaaaaaaaa, 1024) + b'\x00' * 1024,
    'id': struct.pack('<I', 0xaaaaaaaa),
    'id_ver_len': struct.pack('<III', 0x01000000, 0xaaaaaaaa, 1024),
}

target = 0xe3421d1b

# Common 32-bit polynomials:
polys = [
    (0x04C11DB7, "IEEE / MPEG / POSIX"),
    (0xEDB88320, "IEEE rev"),
    (0x1EDC6F41, "Castagnoli"),
    (0x82F63B78, "Castagnoli rev"),
    (0x741B8CD7, "Koopman"),
    (0xEB31D82E, "Koopman rev"),
    (0x000000AF, "CRC-32/XFER"),
]

for name, data in inputs.items():
    # Let's test standard CRC algorithms with crccheck or manual
    for poly, pname in polys:
        # test standard combinations of init and xorout
        for init in [0, 0xFFFFFFFF]:
            for xorout in [0, 0xFFFFFFFF]:
                # unreflected
                crc = init
                for b in data:
                    crc ^= (b << 24)
                    for _ in range(8):
                        if crc & 0x80000000:
                            crc = ((crc << 1) ^ poly) & 0xFFFFFFFF
                        else:
                            crc = (crc << 1) & 0xFFFFFFFF
                crc ^= xorout
                if crc == target:
                    print(f"MATCH unreflected! input={name}, poly={pname}, init={hex(init)}, xorout={hex(xorout)}")

                # reflected
                crc = init
                for b in data:
                    crc ^= b
                    for _ in range(8):
                        if crc & 1:
                            crc = (crc >> 1) ^ poly
                        else:
                            crc = crc >> 1
                crc ^= xorout
                if crc == target:
                    print(f"MATCH reflected! input={name}, poly={pname}, init={hex(init)}, xorout={hex(xorout)}")

print("Done checking common CRC variants.")

