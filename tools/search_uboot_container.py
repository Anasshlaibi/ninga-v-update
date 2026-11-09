with open('firmware/extracted/sec4_parts/part07_u-boot.elf_load_08000000.bin', 'rb') as f:
    data = f.read()

pos = 0
while True:
    pos = data.find(b'\xaa\xaa\xaa\xaa', pos)
    if pos == -1:
        break
    print(f"Offset 0x{pos:x} in u-boot")
    # print context around this offset
    start = max(0, pos - 64)
    end = min(len(data), pos + 64)
    print("Surrounding bytes:", data[start:end].hex())
    pos += 4

