import struct
import os

def build_clean_package():
    base_dir = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab'
    sec_dir = os.path.join(base_dir, 'firmware', 'extracted', 'sections')
    sec3_clean = '/tmp/sec3_spidi.bin' # Exactly 293,747,576 bytes, NO PADDING!
    sec3_len = os.path.getsize(sec3_clean)
    print(f"Clean Section 3 size: {sec3_len} bytes")

    # Read Section 7 original (192 bytes = 8 entries * 24 bytes)
    sec7_orig_path = os.path.join(sec_dir, 'sec7_idx_0x00013000.bin')
    with open(sec7_orig_path, 'rb') as f:
        sec7_data = bytearray(f.read())

    # Entry 4 in Section 7 is Section 3:
    # Entry 4 offset is 4 * 24 = 96 (0x60)
    # Entry 4 words: len(24), magic(b'nibx'), ver(0x30000000), id(0x11111111), pay_len, crc
    entry4_off = 4 * 24
    e_len, e_magic, e_ver, e_id, e_pay_len, e_crc = struct.unpack_from('<I4sIIII', sec7_data, entry4_off)
    print(f"Original Sec 7 Entry 4: magic={e_magic}, ver=0x{e_ver:08x}, id=0x{e_id:08x}, pay_len={e_pay_len}, crc=0x{e_crc:08x}")
    
    # Update pay_len in Entry 4 to exact clean size
    struct.pack_into('<I', sec7_data, entry4_off + 16, sec3_len)
    new_e_pay_len = struct.unpack_from('<I', sec7_data, entry4_off + 16)[0]
    print(f"Updated Sec 7 Entry 4 pay_len: {new_e_pay_len} bytes")

    # Now assemble the clean container:
    out_fw = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab/deploy/ATOMNJV_CLEAN_SPIDI.FW'
    
    global_hdr = struct.pack('<I4sII', 16, b'wfsa', 0x01000000, 8)

    sections_spec = [
        ('sec0_bin_0xaaaaaaaa.bin', b' nib', 0x01000000, 0xaaaaaaaa, 0xe3421d1b, 0x00000000, None),
        ('sec1_bin_0xaaaaaaab.bin', b' nib', 0x01000000, 0xaaaaaaab, 0x9d9abe5f, 0x00000000, None),
        ('sec2_bin_0xaaaaaaa2.bin', b' nib', 0x01000000, 0xaaaaaaa2, 0xa3650bb9, 0x00000000, None),
        ('sec3_clean',              b'nibx', 0x30000000, 0x11111111, 0x989cdecc, 0xffffffff, sec3_clean),
        ('sec4_xbin_0x31323334.bin', b'nibx', 0x30000000, 0x31323334, 0x2182f35e, 0xffffffff, None),
        ('sec5_xbin_0x40404040.bin', b'nibx', 0x30000000, 0x40404040, 0x9ed05ea0, 0xffffffff, None),
        ('sec6_bin_0xaaaaaaa1.bin', b' nib', 0x01000000, 0xaaaaaaa1, 0x200cee75, 0x00000000, None),
        ('sec7_modified',           b' xdi', 0x01000000, 0x00013000, 0x27aee3aa, 0x00000000, sec7_data),
    ]

    with open(out_fw, 'wb') as out_f:
        out_f.write(global_hdr)

        for name, magic, ver, sec_id, crc, trailer_val, custom_data in sections_spec:
            if custom_data is not None:
                if isinstance(custom_data, (bytes, bytearray)):
                    pay_size = len(custom_data)
                    total_len = pay_size + 28
                    sec_hdr = struct.pack('<I4sIIII', total_len, magic, ver, sec_id, pay_size, crc)
                    out_f.write(sec_hdr)
                    out_f.write(custom_data)
                    out_f.write(struct.pack('<I', trailer_val))
                    continue
                else:
                    # It's a file path
                    pay_size = os.path.getsize(custom_data)
                    total_len = pay_size + 28
                    sec_hdr = struct.pack('<I4sIIII', total_len, magic, ver, sec_id, pay_size, crc)
                    out_f.write(sec_hdr)
                    with open(custom_data, 'rb') as in_f:
                        while True:
                            chunk = in_f.read(1024 * 1024)
                            if not chunk: break
                            out_f.write(chunk)
                    out_f.write(struct.pack('<I', trailer_val))
                    continue

            # Standard section
            src_path = os.path.join(sec_dir, name)
            pay_size = os.path.getsize(src_path)
            total_len = pay_size + 28
            sec_hdr = struct.pack('<I4sIIII', total_len, magic, ver, sec_id, pay_size, crc)
            out_f.write(sec_hdr)
            with open(src_path, 'rb') as in_f:
                while True:
                    chunk = in_f.read(1024 * 1024)
                    if not chunk: break
                    out_f.write(chunk)
            out_f.write(struct.pack('<I', trailer_val))

    total_fw_size = os.path.getsize(out_fw)
    print(f"Clean firmware successfully built at: {out_fw}")
    print(f"Total firmware size: {total_fw_size} bytes (clean stream, 0 padding bytes!)")

if __name__ == '__main__':
    build_clean_package()

