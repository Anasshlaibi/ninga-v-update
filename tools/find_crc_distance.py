poly = 0x04C11DB7

def step(crc, byte):
    crc ^= (byte << 24)
    for _ in range(8):
        if crc & 0x80000000:
            crc = ((crc << 1) ^ poly) & 0xFFFFFFFF
        else:
            crc = (crc << 1) & 0xFFFFFFFF
    return crc

# If bit 0 of a byte is set:
# Let's see what CRC value is generated if that bit is at distance k bytes from the end of the input!
target = 0x7ed8a344 # target0 ^ target1

for dist in range(1, 100):
    crc = 0
    # bit 0 set in a byte:
    crc = step(crc, 1)
    # followed by dist zero bytes:
    for _ in range(dist):
        crc = step(crc, 0)
    if crc == target:
        print(f"FOUND EXACT DISTANCE! The changed bit was followed by {dist} bytes!")

print("Distance scan completed.")

