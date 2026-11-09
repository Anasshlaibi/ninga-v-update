import struct

with open('firmware/extracted/sec3_decompressed.img', 'rb') as f:
    boot = f.read(512)
    bytes_per_sector = struct.unpack_from('<H', boot, 11)[0]
    reserved_sectors = struct.unpack_from('<H', boot, 14)[0]
    num_fats = boot[16]
    sectors_per_fat = struct.unpack_from('<H', boot, 22)[0]
    
    fat_offset = reserved_sectors * bytes_per_sector
    f.seek(fat_offset)
    fat_bytes = f.read(sectors_per_fat * bytes_per_sector)
    entries = struct.unpack(f'<{len(fat_bytes)//2}H', fat_bytes)
    
    print(f"FAT entry 0: {hex(entries[0])}")
    print(f"FAT entry 1: {hex(entries[1])}")
    print(f"FAT entry 2: {hex(entries[2])}")
    print(f"FAT entry 3403: {hex(entries[3403])}")
    print(f"FAT entry 3404: {hex(entries[3404])}")
