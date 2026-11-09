import struct

with open('firmware/extracted/sec3_decompressed.img', 'rb') as f:
    f.seek(512)
    fat_bytes = f.read(87 * 512)
    entries = struct.unpack(f'<{len(fat_bytes)//2}H', fat_bytes)
    
    print(f"Cluster 9467: {hex(entries[9467])}")
    print(f"Cluster 9468: {hex(entries[9468])}")
    print(f"Cluster 9469: {hex(entries[9469])}")
