import struct

with open('firmware/extracted/sec3_decompressed.img', 'rb') as f:
    f.seek(512) # FAT starts at sector 1
    fat_data = f.read(512 * 87) # FAT table sectors
    
    entries = struct.unpack(f'<{len(fat_data)//2}H', fat_data)
    free_clusters = [i for i, val in enumerate(entries) if val == 0 and i >= 2]
    print(f"Total FAT entries: {len(entries)}")
    print(f"Free clusters: {len(free_clusters)} ({len(free_clusters) * 16384 / (1024*1024):.2f} MB free)")

    # Find cluster chain for ROOTFS.BIN (start cluster 3403)
    c = 3403
    chain = []
    while c < 0xFFF8 and c != 0:
        chain.append(c)
        c = entries[c]
    print(f"ROOTFS.BIN cluster chain length: {len(chain)} clusters ({len(chain) * 16384} bytes allocated)")
    last_cluster = chain[-1]
    print(f"Last cluster of ROOTFS.BIN: {last_cluster}")
    print(f"Next cluster after last cluster: {entries[last_cluster+1]}")

