with open('firmware/extracted/sec3_decompressed.img', 'rb') as f:
    data = f.read(1024 * 1024 * 4) # read first 4MB (FAT directory entries)
    pos = 0
    while True:
        pos = data.find(b'ROOTFS  BIN', pos)
        if pos == -1:
            break
        print(f"Found 'ROOTFS  BIN' at 0x{pos:x}")
        entry = data[pos:pos+32]
        print("Directory entry:", entry.hex())
        pos += 11

