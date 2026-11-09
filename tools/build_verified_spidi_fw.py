import os
import struct
import zlib

def compute_section_crc(magic, ver, sec_id, pay_len, payload_path, trailer_val):
    total_len = pay_len + 28
    hdr = struct.pack('<I4sIIII', total_len, magic, ver, sec_id, pay_len, 0)
    trailer = struct.pack('<I', trailer_val)
    
    crc = zlib.crc32(hdr, 0xFFFFFFFF)
    with open(payload_path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    crc = zlib.crc32(trailer, crc)
    return crc

def build_verified_firmware():
    base_dir = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab'
    sec_dir = os.path.join(base_dir, 'firmware', 'extracted', 'sections')
    sec3_path = '/tmp/sec3_spidi.bin'
    out_fw = os.path.join(base_dir, 'deploy', 'ATOMNJV_SPIDI_VERIFIED.FW')

    sec3_size = os.path.getsize(sec3_path)
    print(f"1. Custom Section 3 size: {sec3_size} bytes")

    # Compute genuine CRC of custom Section 3
    sec3_crc = compute_section_crc(b'nibx', 0x30000000, 0x11111111, sec3_size, sec3_path, 0xFFFFFFFF)
    print(f"2. Calculated genuine CRC of Section 3: 0x{sec3_crc:08x}")

    # Read original Section 7 (192 bytes)
    sec7_orig_path = os.path.join(sec_dir, 'sec7_idx_0x00013000.bin')
    with open(sec7_orig_path, 'rb') as f:
        sec7_data = bytearray(f.read())
    assert len(sec7_data) == 192, f"Unexpected sec7 size: {len(sec7_data)}"

    # Update Entry 3 in Section 7 (Section 3 entry is at offset 24 + 3*24 = 96 = 0x60)
    entry3_off = 96
    # Check original entry 3 parameters
    t_len, magic, ver, sid, old_pay_len, old_crc = struct.unpack_from('<I4sIIII', sec7_data, entry3_off)
    assert sid == 0x11111111, f"Mismatch on Section 3 ID: 0x{sid:08x}"
    print(f"Original Section 7 Entry 3: pay_len={old_pay_len}, crc=0x{old_crc:08x}")

    # Pack new pay_len and new real CRC into Entry 3
    struct.pack_into('<I', sec7_data, entry3_off + 16, sec3_size)
    struct.pack_into('<I', sec7_data, entry3_off + 20, sec3_crc)
    print(f"Updated Section 7 Entry 3: pay_len={sec3_size}, crc=0x{sec3_crc:08x}")

    # Recompute Section 7 internal table CRC (over bytes 8 to 184)
    sec7_internal_crc = zlib.crc32(sec7_data[8:184], 0xFFFFFFFF)
    struct.pack_into('<I', sec7_data, 4, sec7_internal_crc)
    print(f"3. Updated Section 7 internal table CRC at offset 4: 0x{sec7_internal_crc:08x}")

    # Save updated Section 7 binary to /tmp
    sec7_temp_path = '/tmp/sec7_spidi.bin'
    with open(sec7_temp_path, 'wb') as f:
        f.write(sec7_data)

    # Compute Section 7 container header CRC
    sec7_crc = compute_section_crc(b' xdi', 0x01000000, 0x00013000, 192, sec7_temp_path, 0x00000000)
    print(f"4. Updated Section 7 container header CRC: 0x{sec7_crc:08x}")

    # Build the full firmware package
    sections = [
        ('sec0_bin_0xaaaaaaaa.bin', b' nib', 0x01000000, 0xaaaaaaaa, 1024, 0xe3421d1b, 0x00000000, os.path.join(sec_dir, 'sec0_bin_0xaaaaaaaa.bin')),
        ('sec1_bin_0xaaaaaaab.bin', b' nib', 0x01000000, 0xaaaaaaab, 1024, 0x9d9abe5f, 0x00000000, os.path.join(sec_dir, 'sec1_bin_0xaaaaaaab.bin')),
        ('sec2_bin_0xaaaaaaa2.bin', b' nib', 0x01000000, 0xaaaaaaa2, 1024, 0xa3650bb9, 0x00000000, os.path.join(sec_dir, 'sec2_bin_0xaaaaaaa2.bin')),
        ('sec3_spidi.bin',          b'nibx', 0x30000000, 0x11111111, sec3_size, sec3_crc, 0xffffffff, sec3_path),
        ('sec4_xbin_0x31323334.bin', b'nibx', 0x30000000, 0x31323334, 2097152, 0x2182f35e, 0xffffffff, os.path.join(sec_dir, 'sec4_xbin_0x31323334.bin')),
        ('sec5_xbin_0x40404040.bin', b'nibx', 0x30000000, 0x40404040, 23068672, 0x9ed05ea0, 0xffffffff, os.path.join(sec_dir, 'sec5_xbin_0x40404040.bin')),
        ('sec6_bin_0xaaaaaaa1.bin', b' nib', 0x01000000, 0xaaaaaaa1, 1024, 0x200cee75, 0x00000000, os.path.join(sec_dir, 'sec6_bin_0xaaaaaaa1.bin')),
        ('sec7_spidi.bin',          b' xdi', 0x01000000, 0x00013000, 192, sec7_crc, 0x00000000, sec7_temp_path),
    ]

    global_hdr = struct.pack('<I4sII', 16, b'wfsa', 0x01000000, 8)
    os.makedirs(os.path.dirname(out_fw), exist_ok=True)
    with open(out_fw, 'wb') as out_f:
        out_f.write(global_hdr)
        for name, magic, ver, sid, pay_sz, crc, trl_val, path in sections:
            tot_len = pay_sz + 28
            hdr = struct.pack('<I4sIIII', tot_len, magic, ver, sid, pay_sz, crc)
            trl = struct.pack('<I', trl_val)
            out_f.write(hdr)
            with open(path, 'rb') as in_f:
                while True:
                    c = in_f.read(1024 * 1024)
                    if not c:
                        break
                    out_f.write(c)
            out_f.write(trl)

    total_fw_size = os.path.getsize(out_fw)
    print(f"5. Verified firmware successfully created at: {out_fw}")
    print(f"   Total Size: {total_fw_size:,} bytes")

    # Post-check: Read back out_fw and verify all 8 section CRCs!
    print("6. Performing complete integrity audit of generated container...")
    with open(out_fw, 'rb') as f:
        g_hdr = f.read(16)
        assert g_hdr[4:8] == b'wfsa', "Global header corruption!"
        for name, magic, ver, sid, pay_sz, expected_crc, trl_val, path in sections:
            pos = f.tell()
            s_hdr = f.read(24)
            tot_len, s_mag, s_ver, s_id, s_pay, s_crc = struct.unpack('<I4sIIII', s_hdr)
            assert s_id == sid, f"Section ID mismatch: {hex(s_id)} vs {hex(sid)}"
            assert s_crc == expected_crc, f"Header CRC mismatch for {name}: {hex(s_crc)} vs {hex(expected_crc)}"

            # Compute CRC over actual data in file
            c = zlib.crc32(struct.pack('<I4sIIII', tot_len, s_mag, s_ver, s_id, s_pay, 0), 0xFFFFFFFF)
            read_bytes = 0
            while read_bytes < s_pay:
                chunk = f.read(min(1024 * 1024, s_pay - read_bytes))
                c = zlib.crc32(chunk, c)
                read_bytes += len(chunk)
            trailer = f.read(4)
            c = zlib.crc32(trailer, c)
            assert c == expected_crc, f"Data CRC check failed for {name}: calc {hex(c)} vs exp {hex(expected_crc)}"
            print(f"   [OK] {name:24s}: CRC 0x{c:08x} VERIFIED PERFECT!")

    print("ALL 8 SECTIONS AND INDEX CHECKSUMS 100% VERIFIED!")

if __name__ == '__main__':
    build_verified_firmware()

