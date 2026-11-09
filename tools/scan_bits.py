poly = 0x04C11DB7

def step_byte(crc, byte):
    crc ^= (byte << 24)
    for _ in range(8):
        if crc & 0x80000000:
            crc = ((crc << 1) ^ poly) & 0xFFFFFFFF
        else:
            crc = (crc << 1) & 0xFFFFFFFF
    return crc

target = 0x7ed8a344

for bit in range(8):
    for dist in range(0, 50):
        crc = 0
        crc = step_byte(crc, 1 << bit)
        for _ in range(dist):
            crc = step_byte(crc, 0)
        if crc == target:
            print(f"Match: bit {bit}, followed by {dist} bytes!")

print("Done scan.")

