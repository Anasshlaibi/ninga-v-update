import struct
import os
import shutil
import subprocess

def update_sec3():
    base_dir = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab'
    orig_sec3 = os.path.join(base_dir, 'firmware', 'extracted', 'sec3_decompressed.img')
    work_sec3 = '/tmp/sec3_spidi.img'
    new_rootfs_path = '/tmp/ROOTFS_spidi.BIN'

    print("1. Reading new ROOTFS.BIN...")
    with open(new_rootfs_path, 'rb') as f:
        new_rootfs = f.read()
    new_size = len(new_rootfs)
    print(f"New ROOTFS.BIN size: {new_size} bytes")

    print("2. Copying original sec3_decompressed.img...")
    shutil.copyfile(orig_sec3, work_sec3)

    # Boot sector parameters
    with open(work_sec3, 'r+b') as f:
        f.seek(0)
        boot = f.read(512)
        bytes_per_sector = struct.unpack_from('<H', boot, 11)[0]
        sectors_per_cluster = boot[13]
        reserved_sectors = struct.unpack_from('<H', boot, 14)[0]
        num_fats = boot[16]
        root_entries = struct.unpack_from('<H', boot, 17)[0]
        sectors_per_fat = struct.unpack_from('<H', boot, 22)[0]

        fat1_offset = reserved_sectors * bytes_per_sector
        fat2_offset = fat1_offset + sectors_per_fat * bytes_per_sector
        root_dir_offset = fat1_offset + (num_fats * sectors_per_fat * bytes_per_sector)
        root_dir_size = root_entries * 32
        data_offset = root_dir_offset + root_dir_size
        bytes_per_cluster = bytes_per_sector * sectors_per_cluster

        # Calculate clusters needed
        clusters_needed = (new_size + bytes_per_cluster - 1) // bytes_per_cluster
        start_cluster = 3403
        end_cluster = start_cluster + clusters_needed - 1
        print(f"Allocating {clusters_needed} clusters from {start_cluster} to {end_cluster}...")

        # Update FAT1 and FAT2
        for fat_off in [fat1_offset, fat2_offset]:
            f.seek(fat_off + start_cluster * 2)
            # Write continuous chain: cluster i points to i+1
            chain = [c + 1 for c in range(start_cluster, end_cluster)] + [0xFFFF]
            f.write(struct.pack(f'<{len(chain)}H', *chain))

        # Update Root Directory entry for ROOTFS.BIN (offset 0x304a0)
        f.seek(0x304a0)
        dirent = bytearray(f.read(32))
        assert dirent[:11] == b'ROOTFS  BIN', "Directory entry mismatch!"
        # Update file size at bytes 28-31
        struct.pack_into('<I', dirent, 28, new_size)
        f.seek(0x304a0)
        f.write(dirent)

        # Write new ROOTFS.BIN data at cluster 3403
        cluster_offset = data_offset + (start_cluster - 2) * bytes_per_cluster
        f.seek(cluster_offset)
        f.write(new_rootfs)

    print("3. sec3_spidi.img successfully patched!")

if __name__ == '__main__':
    update_sec3()
