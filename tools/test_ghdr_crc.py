import struct
import zlib

ghdr = bytes.fromhex('10000000776673610000000108000000')
target = 0xe96d36e8

print("zlib.crc32(ghdr):", hex(zlib.crc32(ghdr)))

# Let's search across all possible 32-bit polynomials:
for poly in [0x04C11DB7, 0xEDB88320, 0x1EDC6F41, 0x82F63B78, 0x741B8CD7, 0xEB31D82E, 0x000000AF, 0x5D6DCB, 0x8005]:
    for init in [0, 0xFFFFFFFF, 0x46AF6449]:
        for xorout in [0, 0xFFFFFFFF]:
            crc = init
            for b in ghdr:
                crc ^= (b << 24)
                for _ in range(8):
                    if crc & 0x80000000:
                        crc = ((crc << 1) ^ poly) & 0xFFFFFFFF
                    else:
                        crc = (crc << 1) & 0xFFFFFFFF
            crc ^= xorout
            if crc == target:
                print(f"MATCH unreflected! poly={hex(poly)}, init={hex(init)}, xorout={hex(xorout)}")

            crc = init
            for b in ghdr:
                crc ^= b
                for _ in range(8):
                    if crc & 1:
                        crc = (crc >> 1) ^ poly
                    else:
                        crc = crc >> 1
            crc ^= xorout
            if crc == target:
                print(f"MATCH reflected! poly={hex(poly)}, init={hex(init)}, xorout={hex(xorout)}")

