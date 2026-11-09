with open('firmware/extracted/sec4_parts/part07_u-boot.elf_load_08000000.bin', 'rb') as f:
    data = f.read()

for crc_val in [0xe3421d1b, 0x9d9abe5f, 0x989cdecc, 0x27aee3aa, 0xe96d36e8]:
    b = crc_val.to_bytes(4, 'little')
    if b in data:
        print(f"Found {hex(crc_val)} little-endian in u-boot")
    b = crc_val.to_bytes(4, 'big')
    if b in data:
        print(f"Found {hex(crc_val)} big-endian in u-boot")

