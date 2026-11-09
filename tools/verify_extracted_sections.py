import hashlib
import os

R = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab'
sec_dir = os.path.join(R, 'firmware', 'extracted', 'sections')

sections = [
    ('sec0_bin_0xaaaaaaaa.bin', 1024),
    ('sec1_bin_0xaaaaaaab.bin', 1024),
    ('sec2_bin_0xaaaaaaa2.bin', 1024),
    ('sec3_xbin_0x11111111.bin', 294387712),
    ('sec4_xbin_0x31323334.bin', 2097152),
    ('sec5_xbin_0x40404040.bin', 23068672),
    ('sec6_bin_0xaaaaaaa1.bin', 1024),
    ('sec7_idx_0x00013000.bin', 192),
]

for fn, exp_len in sections:
    p = os.path.join(sec_dir, fn)
    with open(p, 'rb') as f:
        data = f.read()
    h = hashlib.sha256(data).hexdigest()
    print(f"{fn:30s}: size={len(data):10d} (matches: {len(data) == exp_len}), sha256={h[:16]}...")

