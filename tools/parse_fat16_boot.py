import struct

with open('firmware/extracted/sec3_decompressed.img', 'rb') as f:
    boot = f.read(512)
    bytes_per_sector = struct.unpack_from('<H', boot, 11)[0]
    sectors_per_cluster = boot[13]
    reserved_sectors = struct.unpack_from('<H', boot, 14)[0]
    num_fats = boot[16]
    root_entries = struct.unpack_from('<H', boot, 17)[0]
    total_sectors_16 = struct.unpack_from('<H', boot, 19)[0]
    sectors_per_fat = struct.unpack_from('<H', boot, 22)[0]
    total_sectors_32 = struct.unpack_from('<I', boot, 32)[0]

total_sectors = total_sectors_32 if total_sectors_16 == 0 else total_sectors_16

fat_start = reserved_sectors * bytes_per_sector
root_dir_start = fat_start + (num_fats * sectors_per_fat * bytes_per_sector)
root_dir_size = root_entries * 32
data_start = root_dir_start + root_dir_size
bytes_per_cluster = bytes_per_sector * sectors_per_cluster

print(f"Bytes per sector: {bytes_per_sector}")
print(f"Sectors per cluster: {sectors_per_cluster} ({bytes_per_cluster} bytes/cluster)")
print(f"Reserved sectors: {reserved_sectors}")
print(f"FAT start: 0x{fat_start:x}")
print(f"Root dir start: 0x{root_dir_start:x}")
print(f"Data start: 0x{data_start:x}")

cluster_3403_offset = data_start + (3403 - 2) * bytes_per_cluster
print(f"Cluster 3403 byte offset: 0x{cluster_3403_offset:x}")

# Verify cluster 3403 matches ROOTFS.BIN first 16 bytes
f.seek(cluster_3403_offset)
first16_img = f.read(16)

with open('firmware/extracted/fat16_fs/ROOTFS.BIN', 'rb') as rf:
    first16_rootfs = rf.read(16)

print(f"Data at cluster 3403: {first16_img.hex()}")
print(f"ROOTFS.BIN first 16:   {first16_rootfs.hex()}")
assert first16_img == first16_rootfs, "Mismatch!"
print("EXACT MATCH: Cluster 3403 points directly to ROOTFS.BIN!")

