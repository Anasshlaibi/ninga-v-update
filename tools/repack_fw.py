import os
import struct
import hashlib

def repack_fw(output_path, sec3_payload_path=None):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sec_dir = os.path.join(base_dir, 'firmware', 'extracted', 'sections')

    # Global header (16 bytes)
    # <I4sII : 16, b'wfsa', 0x01000000, 8
    global_hdr = struct.pack('<I4sII', 16, b'wfsa', 0x01000000, 8)

    # Section specifications: (filename, magic, version, section_id, expected_crc, trailer)
    sections_spec = [
        ('sec0_bin_0xaaaaaaaa.bin', b' nib', 0x01000000, 0xaaaaaaaa, 0xe3421d1b, 0x00000000),
        ('sec1_bin_0xaaaaaaab.bin', b' nib', 0x01000000, 0xaaaaaaab, 0x9d9abe5f, 0x00000000),
        ('sec2_bin_0xaaaaaaa2.bin', b' nib', 0x01000000, 0xaaaaaaa2, 0xa3650bb9, 0x00000000),
        ('sec3_xbin_0x11111111.bin', b'nibx', 0x30000000, 0x11111111, 0x989cdecc, 0xffffffff),
        ('sec4_xbin_0x31323334.bin', b'nibx', 0x30000000, 0x31323334, 0x2182f35e, 0xffffffff),
        ('sec5_xbin_0x40404040.bin', b'nibx', 0x30000000, 0x40404040, 0x9ed05ea0, 0xffffffff),
        ('sec6_bin_0xaaaaaaa1.bin', b' nib', 0x01000000, 0xaaaaaaa1, 0x200cee75, 0x00000000),
        ('sec7_idx_0x00013000.bin', b' xdi', 0x01000000, 0x00013000, 0x27aee3aa, 0x00000000),
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as out_f:
        out_f.write(global_hdr)

        for fn, magic, ver, sec_id, crc, trailer_val in sections_spec:
            if fn == 'sec3_xbin_0x11111111.bin' and sec3_payload_path is not None:
                src_path = sec3_payload_path
            else:
                src_path = os.path.join(sec_dir, fn)

            pay_size = os.path.getsize(src_path)
            total_len = pay_size + 28  # 24 header + pay_size + 4 trailer
            sec_hdr = struct.pack('<I4sIIII', total_len, magic, ver, sec_id, pay_size, crc)
            trailer = struct.pack('<I', trailer_val)

            out_f.write(sec_hdr)
            with open(src_path, 'rb') as in_f:
                # stream in 1MB chunks to keep memory usage low
                while True:
                    chunk = in_f.read(1024 * 1024)
                    if not chunk:
                        break
                    out_f.write(chunk)
            out_f.write(trailer)

    print(f"Repacked firmware successfully written to: {output_path}")

if __name__ == '__main__':
    import sys
    test_out = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab/firmware/extracted/test_roundtrip.fw'
    repack_fw(test_out)

    # Verify SHA256 matches original ATOMNJV.FW
    orig_path = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab/firmware/original/ATOMNJV.FW'
    
    def get_sha256(p):
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            while True:
                c = f.read(1024 * 1024)
                if not c:
                    break
                h.update(c)
        return h.hexdigest()

    h_orig = get_sha256(orig_path)
    h_test = get_sha256(test_out)
    print(f"Original SHA256: {h_orig}")
    print(f"Repacked SHA256: {h_test}")
    assert h_orig == h_test, "SHA256 mismatch!"
    print("VERIFICATION SUCCESSFUL: Repacked container matches original byte-for-byte!")
    # clean up test file
    os.remove(test_out)

