# Let's test linearity between Sec 0, 1, 2, 6
crc0 = 0xe3421d1b
crc1 = 0x9d9abe5f
crc2 = 0xa3650bb9
crc6 = 0x200cee75

d0_1 = crc0 ^ crc1 # delta for bit 0 (0xaaaaaaaa vs 0xaaaaaaab)
d0_2 = crc0 ^ crc2 # delta for bit 3 (0x...a vs 0x...2: 1010 vs 0010 -> bit 3 changed)
d0_6 = crc0 ^ crc6 # delta for (0x...a vs 0x...1: 1010 vs 0001 -> bit 3, bit 1, bit 0 changed)

print(f"delta(bit 0): {hex(d0_1)}")
print(f"delta(bit 3): {hex(d0_2)}")
print(f"delta(bit 3, 1, 0): {hex(d0_6)}")

# From this, delta(bit 1) should be:
d_bit1 = d0_6 ^ d0_1 ^ d0_2
print(f"Inferred delta(bit 1): {hex(d_bit1)}")

# In a standard CRC, if bit 0 delta is D, then bit 1 delta is (D >> 1) ^ poly (or (D << 1) ^ poly)!
# Let's check both:
# Case 1: right-shift (reflected)
# If D = d0_1:
for poly in [0xEDB88320, 0x82F63B78, 0xEB31D82E]:
    next_d = (d0_1 >> 1) ^ (poly if (d0_1 & 1) else 0)
    print(f"Reflected step with poly {hex(poly)}: {hex(next_d)} (target: {hex(d_bit1)})")

# Case 2: left-shift (unreflected)
for poly in [0x04C11DB7, 0x1EDC6F41, 0x741B8CD7]:
    next_d = ((d0_1 << 1) & 0xffffffff) ^ (poly if (d0_1 & 0x80000000) else 0)
    print(f"Unreflected step with poly {hex(poly)}: {hex(next_d)} (target: {hex(d_bit1)})")
