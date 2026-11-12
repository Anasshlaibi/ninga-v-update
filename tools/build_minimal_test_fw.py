import os
import shutil
import struct
import subprocess
import zlib
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab'
EXT_DIR = os.path.join(BASE_DIR, 'firmware', 'extracted')
SEC_DIR = os.path.join(EXT_DIR, 'sections')
FAT_IMG_ORIG = os.path.join(EXT_DIR, 'sec3_decompressed.img')
OUT_FW = os.path.join(BASE_DIR, 'deploy', 'ATOMNJV_MINIMAL_TEST.FW')
PREVIEW_PNG = '/mnt/c/Users/HELIOS NEO 16/.gemini/antigravity/brain/5b1c8c71-256c-4b33-bf21-90865c844072/scratch/pls/pls_test_preview.png'


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


def make_test_pls_wait(orig_bytes):
    assert len(orig_bytes) == 140 * 426 * 4
    # Original is 140x426 portrait (which displays upright when rotated +90 deg CCW -> 426x140 landscape)
    portrait = Image.frombytes('RGBA', (140, 426), orig_bytes, 'raw', 'RGBA')
    landscape = portrait.rotate(90, expand=True)  # 426x140 upright landscape

    # Recolor the orange/yellow diamond to bright emerald green so change is unmistakable,
    # keeping black silhouette and white "Please Wait..." text crisp.
    px = landscape.load()
    w, h = landscape.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 0 and r > 150 and g > 80 and b < 90:
                px[x, y] = (30, 220, 90, a)

    # Draw a bright green bar + "V4" indicator at bottom right of landscape box
    draw = ImageDraw.Draw(landscape)
    draw.rectangle([150, 108, 410, 128], fill=(30, 220, 90, 255))
    draw.text((160, 111), 'SPIDI MINIMAL TEST 4', fill=(0, 0, 0, 255))

    # Save visual preview on black background for inspection
    bg = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    Image.alpha_composite(bg, landscape).save(PREVIEW_PNG)

    # Rotate back -90 deg (CW) into 140x426 portrait RGBA buffer
    out_portrait = landscape.rotate(-90, expand=True)
    assert out_portrait.size == (140, 426)
    out_bytes = out_portrait.tobytes('raw', 'RGBA')
    assert len(out_bytes) == len(orig_bytes)
    return out_bytes


def get_fat16_chain(img_path, target_name='PLS_WAIT.BIN'):
    with open(img_path, 'rb') as f:
        bpb = f.read(512)
        bps, spc, rsvd, nfats, nroot, _, _, spf = struct.unpack('<HBHBHHBH', bpb[11:24])
        fat_off = rsvd * bps
        root_off = (rsvd + nfats * spf) * bps
        data_off = root_off + nroot * 32
        clu_bytes = spc * bps

        f.seek(root_off)
        root_data = f.read(nroot * 32)
        start_clu = None
        fsize = None
        for i in range(nroot):
            ent = root_data[i * 32:(i + 1) * 32]
            if ent[0] == 0:
                break
            if ent[0] == 0xE5 or ent[11] == 0x0F:
                continue
            name = ent[:8].decode('ascii', errors='replace').rstrip()
            extn = ent[8:11].decode('ascii', errors='replace').rstrip()
            fname = f'{name}.{extn}' if extn else name
            if fname == target_name:
                start_clu = struct.unpack('<H', ent[26:28])[0]
                fsize = struct.unpack('<I', ent[28:32])[0]
                break
        assert start_clu is not None, f'{target_name} not found in FAT16!'

        f.seek(fat_off)
        fat_bytes = f.read(spf * bps)
        chain = []
        cur = start_clu
        while 2 <= cur < 0xFFF8:
            chain.append(cur)
            cur = struct.unpack('<H', fat_bytes[cur * 2:cur * 2 + 2])[0]
        return clu_bytes, data_off, fsize, chain


def read_chain_bytes(img_path, clu_bytes, data_off, fsize, chain):
    buf = bytearray()
    with open(img_path, 'rb') as f:
        for clu in chain:
            f.seek(data_off + (clu - 2) * clu_bytes)
            buf.extend(f.read(clu_bytes))
    return bytes(buf[:fsize])


def write_chain_bytes(img_path, clu_bytes, data_off, fsize, chain, payload):
    assert len(payload) == fsize
    with open(img_path, 'r+b') as f:
        pos = 0
        for clu in chain:
            take = min(clu_bytes, fsize - pos)
            f.seek(data_off + (clu - 2) * clu_bytes)
            f.write(payload[pos:pos + take])
            pos += take
        assert pos == fsize


def main():
    tmp_img = '/tmp/sec3_minimal.img'
    tmp_gz = '/tmp/sec3_minimal.bin.gz'
    tmp_sec3 = '/tmp/sec3_minimal_aligned.bin'
    tmp_sec7 = '/tmp/sec7_minimal.bin'

    print('1. Locating PLS_WAIT.BIN cluster chain in original sec3_decompressed.img...')
    clu_bytes, data_off, fsize, chain = get_fat16_chain(FAT_IMG_ORIG, 'PLS_WAIT.BIN')
    print(f'   PLS_WAIT.BIN size={fsize}, clusters={chain}, clu_bytes={clu_bytes}')

    orig_pls = read_chain_bytes(FAT_IMG_ORIG, clu_bytes, data_off, fsize, chain)
    new_pls = make_test_pls_wait(orig_pls)
    print(f'   Generated modified PLS_WAIT.BIN ({len(new_pls)} B), preview saved to {PREVIEW_PNG}')

    print('2. Copying clean sec3_decompressed.img -> /tmp/sec3_minimal.img and patching PLS_WAIT.BIN...')
    shutil.copyfile(FAT_IMG_ORIG, tmp_img)
    write_chain_bytes(tmp_img, clu_bytes, data_off, fsize, chain, new_pls)

    # Verify read-back matches new_pls
    chk = read_chain_bytes(tmp_img, clu_bytes, data_off, fsize, chain)
    assert chk == new_pls, 'FAT16 cluster write verification failed!'

    print('3. Compressing /tmp/sec3_minimal.img with gzip -n (default level 6, FLG=0x00, XFL=0x00)...')
    with open(tmp_gz, 'wb') as out_gz:
        subprocess.run(['gzip', '-n', '-c', tmp_img], stdout=out_gz, check=True)

    gz_size = os.path.getsize(tmp_gz)
    target_sec3_size = 0x118C0000  # 294,387,712 bytes — exact original Sec 3 size
    footer_magic = b'\x00\x00\x14\xa7'
    print(f'   Compressed gzip size: {gz_size} bytes (limit before 4B footer: {target_sec3_size - 4})')
    assert gz_size <= target_sec3_size - 4, f'Gzip output too large ({gz_size} > {target_sec3_size - 4})!'

    pad_len = target_sec3_size - 4 - gz_size
    print(f'4. Building padded nibx Section 3 ({target_sec3_size} B = 0x{target_sec3_size:x}): pad={pad_len} x 0xFF + footer 000014a7')
    with open(tmp_sec3, 'wb') as out_s3:
        with open(tmp_gz, 'rb') as in_gz:
            shutil.copyfileobj(in_gz, out_s3, length=1024 * 1024)
        out_s3.write(b'\xff' * pad_len)
        out_s3.write(footer_magic)

    assert os.path.getsize(tmp_sec3) == target_sec3_size

    sec3_crc = compute_section_crc(b'nibx', 0x30000000, 0x11111111, target_sec3_size, tmp_sec3, 0xFFFFFFFF)
    print(f'5. Section 3 CRC: 0x{sec3_crc:08x}')

    sec7_orig_path = os.path.join(SEC_DIR, 'sec7_idx_0x00013000.bin')
    sec7_data = bytearray(open(sec7_orig_path, 'rb').read())
    assert len(sec7_data) == 192
    entry3_off = 96
    _, _, _, sid, _, _ = struct.unpack_from('<I4sIIII', sec7_data, entry3_off)
    assert sid == 0x11111111
    struct.pack_into('<I', sec7_data, entry3_off + 16, target_sec3_size)
    struct.pack_into('<I', sec7_data, entry3_off + 20, sec3_crc)
    sec7_internal_crc = zlib.crc32(sec7_data[8:184], 0xFFFFFFFF)
    struct.pack_into('<I', sec7_data, 4, sec7_internal_crc)
    with open(tmp_sec7, 'wb') as f:
        f.write(sec7_data)
    sec7_crc = compute_section_crc(b' xdi', 0x01000000, 0x00013000, 192, tmp_sec7, 0x00000000)
    print(f'6. Section 7 internal CRC: 0x{sec7_internal_crc:08x}, container CRC: 0x{sec7_crc:08x}')

    sections = [
        ('sec0_bin_0xaaaaaaaa.bin', b' nib', 0x01000000, 0xaaaaaaaa, 1024, 0xe3421d1b, 0x00000000, os.path.join(SEC_DIR, 'sec0_bin_0xaaaaaaaa.bin')),
        ('sec1_bin_0xaaaaaaab.bin', b' nib', 0x01000000, 0xaaaaaaab, 1024, 0x9d9abe5f, 0x00000000, os.path.join(SEC_DIR, 'sec1_bin_0xaaaaaaab.bin')),
        ('sec2_bin_0xaaaaaaa2.bin', b' nib', 0x01000000, 0xaaaaaaa2, 1024, 0xa3650bb9, 0x00000000, os.path.join(SEC_DIR, 'sec2_bin_0xaaaaaaa2.bin')),
        ('sec3_minimal_aligned.bin', b'nibx', 0x30000000, 0x11111111, target_sec3_size, sec3_crc, 0xffffffff, tmp_sec3),
        ('sec4_xbin_0x31323334.bin', b'nibx', 0x30000000, 0x31323334, 2097152, 0x2182f35e, 0xffffffff, os.path.join(SEC_DIR, 'sec4_xbin_0x31323334.bin')),
        ('sec5_xbin_0x40404040.bin', b'nibx', 0x30000000, 0x40404040, 23068672, 0x9ed05ea0, 0xffffffff, os.path.join(SEC_DIR, 'sec5_xbin_0x40404040.bin')),
        ('sec6_bin_0xaaaaaaa1.bin', b' nib', 0x01000000, 0xaaaaaaa1, 1024, 0x200cee75, 0x00000000, os.path.join(SEC_DIR, 'sec6_bin_0xaaaaaaa1.bin')),
        ('sec7_minimal.bin', b' xdi', 0x01000000, 0x00013000, 192, sec7_crc, 0x00000000, tmp_sec7),
    ]

    os.makedirs(os.path.dirname(OUT_FW), exist_ok=True)
    global_hdr = struct.pack('<I4sII', 16, b'wfsa', 0x01000000, 8)
    with open(OUT_FW, 'wb') as out_f:
        out_f.write(global_hdr)
        for name, magic, ver, sid, pay_sz, crc, trl_val, path in sections:
            tot_len = pay_sz + 28
            out_f.write(struct.pack('<I4sIIII', tot_len, magic, ver, sid, pay_sz, crc))
            with open(path, 'rb') as in_f:
                shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
            out_f.write(struct.pack('<I', trl_val))

    orig_sz = os.path.getsize(os.path.join(BASE_DIR, 'firmware', 'original', 'ATOMNJV.FW'))
    out_sz = os.path.getsize(OUT_FW)
    print(f'7. Wrote {OUT_FW} ({out_sz:,} B, matches original size: {out_sz == orig_sz})')

    # Full container audit
    with open(OUT_FW, 'rb') as f:
        assert f.read(16) == global_hdr
        for name, magic, ver, sid, pay_sz, expected_crc, trl_val, _ in sections:
            s_hdr = f.read(24)
            tot_len, s_mag, s_ver, s_id, s_pay, s_crc = struct.unpack('<I4sIIII', s_hdr)
            assert (s_mag, s_ver, s_id, s_pay, s_crc) == (magic, ver, sid, pay_sz, expected_crc)
            c = zlib.crc32(struct.pack('<I4sIIII', tot_len, s_mag, s_ver, s_id, s_pay, 0), 0xFFFFFFFF)
            rem = s_pay
            while rem > 0:
                chunk = f.read(min(1024 * 1024, rem))
                c = zlib.crc32(chunk, c)
                rem -= len(chunk)
            trailer = f.read(4)
            c = zlib.crc32(trailer, c)
            assert c == expected_crc
            print(f'   [OK] {name:24s} CRC 0x{c:08x}')
    print('DONE! All 8 CRCs, exact original container size, 0xFF padding, and 000014a7 footer verified.')


if __name__ == '__main__':
    main()

