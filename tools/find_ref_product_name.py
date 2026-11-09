import struct

with open('firmware/extracted/rootfs_ext4/usr/bin/core_control', 'rb') as f:
    data = f.read()

# Let's search for adrp/add loading 0x81ec8
# In 64-bit ARM, 0x81ec8 is page 0x81000 + 0xec8
target_page = 0x81000
target_page_alt = 0x82000

for i in range(0, len(data) - 4, 4):
    word = struct.unpack_from('<I', data, i)[0]
    # Check if adrp
    if (word & 0x9f000000) == 0x90000000:
        immlo = (word >> 29) & 3
        immhi = (word >> 5) & 0x7ffff
        imm = (immhi << 2) | immlo
        if imm & (1 << 20):
            imm -= (1 << 21)
        pc_page = (i) & ~0xfff
        page = pc_page + (imm << 12)
        if page == target_page:
            # Check next instruction for add with 0xec8
            next_word = struct.unpack_from('<I', data, i + 4)[0]
            if (next_word & 0x7f800000) == 0x11000000: # add imm
                imm12 = (next_word >> 10) & 0xfff
                if imm12 == 0xec8:
                    print(f"Reference at pc = 0x{i:x}")

