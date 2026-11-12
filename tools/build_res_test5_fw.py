#!/usr/bin/env python3
"""
Test #5 Firmware Builder: Isolated RES0001.BIN UI Modification
-------------------------------------------------------------
Keeps every section (0, 1, 2, 4, 5, 6) and every FAT16 file inside Section 3
(including ROOTFS.BIN, APP0000.BIN, DATA0000.BIN, FLASH.UB, RAMDISK.UB, PLS_WAIT.BIN)
100% factory stock, modifying ONLY RES0001.BIN in-place without shifting
Chunk 0 decompressed offsets or exceeding RES0001.BIN's existing 175-cluster chain.

Uses the exact Section 3 container packing verified on real Ninja V hardware in Test #4:
  - gzip -n (default level 6, FLG=0x00, XFL=0x00)
  - 0xFF padding + 4-byte 0x000014a7 footer -> 0x118C0000 bytes
  - Recomputed Section 3 and Section 7 CRC-32s
"""

import os
import shutil
import struct
import subprocess
import zlib
import numpy as np
from PIL import Image, ImageDraw

BASE_DIR = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab'
EXT_DIR = os.path.join(BASE_DIR, 'firmware', 'extracted')
SEC_DIR = os.path.join(EXT_DIR, 'sections')
FAT_IMG_ORIG = os.path.join(EXT_DIR, 'sec3_decompressed.img')
OUT_FW = os.path.join(BASE_DIR, 'deploy', 'ATOMNJV_RES_TEST5.FW')
OUT_RES_COPY = '/tmp/RES0001_test5.BIN'
PREVIEW_PNG = '/mnt/c/Users/HELIOS NEO 16/.gemini/antigravity/brain/5b1c8c71-256c-4b33-bf21-90865c844072/scratch/pls/test5_res_preview.png'


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


def decode_packbits32(data):
    i = 0
    n = len(data)
    out = []
    while i < n:
        c = data[i]
        i += 1
        if c == 0x80:
            continue
        elif c < 0x80:
            need = (c + 1) * 4
            assert i + need <= n, f'Truncated PackBits-32 literal at {i - 1}'
            out.append(data[i:i + need])
            i += need
        else:
            assert i + 4 <= n, f'Truncated PackBits-32 repeat at {i - 1}'
            out.append(data[i:i + 4] * (257 - c))
            i += 4
    return b''.join(out)


def encode_packbits32(raw):
    assert len(raw) % 4 == 0
    w = np.frombuffer(raw, dtype=np.uint32)
    n = len(w)
    out = bytearray()
    mv = memoryview(raw)
    i = 0
    while i < n:
        wi = w[i]
        run = 1
        while i + run < n and run < 128 and w[i + run] == wi:
            run += 1
        if run >= 2:
            out.append(257 - run)
            out.extend(mv[i * 4:(i + 1) * 4])
            i += run
        else:
            lit_start = i
            i += 1
            while i < n and (i - lit_start) < 128:
                if i + 2 < n and w[i] == w[i + 1] == w[i + 2]:
                    break
                if i + 1 < n and w[i] == w[i + 1] and (i - lit_start) >= 1:
                    break
                i += 1
            cnt = i - lit_start
            out.append(cnt - 1)
            out.extend(mv[lit_start * 4:i * 4])
    return bytes(out)


def tint_emerald_rgba(px_slice, tint_dark_bg=True, preserve_glyph_contrast=False):
    """
    Recolors an (N, 4) uint8 RGBA slice in-place to vivid emerald green while
    preserving original alpha and smooth anti-aliasing luminance.
    When preserve_glyph_contrast=True, saturated colored pill/circle backgrounds
    map to deep emerald (12, 130, 58) while neutral foreground glyphs map to crisp white-mint.
    """
    rgb = px_slice[:, :3].astype(np.float32)
    alpha = px_slice[:, 3]
    lum = rgb.max(axis=1)
    chroma = lum - rgb.min(axis=1)

    vis = alpha > 0
    if preserve_glyph_contrast:
        colored_bg = vis & (lum >= 25.0) & (chroma >= 20.0)
        neutral_fg = vis & (lum >= 25.0) & (chroma < 20.0)
        # Check if neutral_fg is the outer grey outline vs glyph on black-backed buttons
        px_slice[colored_bg, 0] = 12
        px_slice[colored_bg, 1] = 135
        px_slice[colored_bg, 2] = 60
        px_slice[neutral_fg, 0] = np.clip(lum[neutral_fg] * 0.90, 0, 255).astype(np.uint8)
        px_slice[neutral_fg, 1] = np.clip(lum[neutral_fg] * 1.00, 0, 255).astype(np.uint8)
        px_slice[neutral_fg, 2] = np.clip(lum[neutral_fg] * 0.92, 0, 255).astype(np.uint8)
    else:
        bright = vis & (lum >= 25.0)
        px_slice[bright, 0] = np.clip(lum[bright] * 0.12, 0, 255).astype(np.uint8)
        px_slice[bright, 1] = np.clip(lum[bright] * 1.00, 0, 255).astype(np.uint8)
        px_slice[bright, 2] = np.clip(lum[bright] * 0.38, 0, 255).astype(np.uint8)

    if tint_dark_bg:
        dark = vis & (lum < 25.0)
        # Subtle dark emerald fill on opaque/semi-opaque button backings
        px_slice[dark, 0] = 6
        px_slice[dark, 1] = 44
        px_slice[dark, 2] = 18


def yuv_to_rgb_img(u1_view):
    # u1_view shape: (H, W_pairs, 4) -> [U, Y0, V, Y1]
    h, wp, _ = u1_view.shape
    w = wp * 2
    u = u1_view.astype(np.float32)
    Y = np.empty((h, w), dtype=np.float32)
    Y[:, 0::2] = u[:, :, 1]
    Y[:, 1::2] = u[:, :, 3]
    U = np.repeat(u[:, :, 0:1], 2, axis=1).reshape(h, w) - 128.0
    V = np.repeat(u[:, :, 2:3], 2, axis=1).reshape(h, w) - 128.0
    R = np.clip(Y + 1.402 * V, 0, 255).astype(np.uint8)
    G = np.clip(Y - 0.344136 * U - 0.714136 * V, 0, 255).astype(np.uint8)
    B = np.clip(Y + 1.772 * U, 0, 255).astype(np.uint8)
    return Image.fromarray(np.stack([R, G, B], axis=-1), 'RGB')


def render_rgba_rot90(px_flat, w, cols):
    seg = px_flat[:w * cols].reshape(cols, w, 4)
    bg = Image.new('RGBA', (w, cols), (10, 14, 12, 255))
    return Image.alpha_composite(bg, Image.fromarray(seg, 'RGBA')).rotate(90, expand=True)


def patch_res0001(orig_res):
    hdr0 = bytearray(orig_res[:16])
    c0_len = struct.unpack('<I', hdr0[12:16])[0]
    c1_off = 16 + c0_len
    hdr1 = bytearray(orig_res[c1_off:c1_off + 16])
    c1_len = struct.unpack('<I', hdr1[12:16])[0]
    assert c1_off + 16 + c1_len == len(orig_res), 'Unexpected trailing bytes in RES0001.BIN'

    c0_enc = orig_res[16:c1_off]
    c1_enc = orig_res[c1_off + 16:]

    print('   Decoding Chunk 0 & Chunk 1 and testing baseline PackBits-32 round-trip...')
    d0_orig = decode_packbits32(c0_enc)
    d1_orig = decode_packbits32(c1_enc)
    assert len(d0_orig) == 80441908
    assert len(d1_orig) == 4423680

    # Copy buffers for modification
    d0_buf = bytearray(d0_orig)
    d1_buf = bytearray(d1_orig)
    arr0_orig = np.frombuffer(d0_orig, dtype=np.uint8).reshape(-1, 4)
    arr0 = np.frombuffer(d0_buf, dtype=np.uint8).reshape(-1, 4)

    # Verified isolated Chunk 0 targets (exact zero-shifted, fixed dimensions):
    targets = [
        ('MENU (112x112)', 2937324, 112, 112, True, False),
        ('REC pills 1&3 (neutral outline)', 7806355, 72, 72, True, False),
        ('REC pill 2 (active filled contrast)', 7806355 + 72 * 72, 72, 72, True, True),
        ('REC pill 3 (neutral outline)', 7806355 + 144 * 72, 72, 72, True, False),
        ('NO INPUT + Orbit (177x100)', 12131724, 100, 177, True, False),
        ('Top Icons w=48 (10x48x48 contrast)', 12281244, 48, 480, True, True),
        ('Menu Tabs w=96 (Input/Info/Record/Monitor)', 14508085, 96, 9600, True, False),
    ]
    for label, start, w, cols, tint_bg, contrast_mode in targets:
        end = start + w * cols
        print(f'   Tinting {label}: u32[{start}..{end}] ({w}x{cols})')
        tint_emerald_rgba(arr0[start:end], tint_dark_bg=tint_bg, preserve_glyph_contrast=contrast_mode)

    # Chunk 1 wallpaper: 2048x1080 UYVY ([U, Y0, V, Y1] -> 1080 x 1024 words).
    # Leave cols 960..1023 (right stride pad 1920..2047) untouched; set active 1920x1080 chroma to emerald.
    u1_orig = np.frombuffer(d1_orig, dtype=np.uint8).reshape(1080, 1024, 4)
    u1 = np.frombuffer(d1_buf, dtype=np.uint8).reshape(1080, 1024, 4)
    u1[:, :960, 0] = 82   # U (low U + low V => pure emerald green)
    u1[:, :960, 2] = 74   # V
    u1[:, :960, 1] = np.clip(u1[:, :960, 1].astype(np.int16) + 18, 0, 235).astype(np.uint8)
    u1[:, :960, 3] = np.clip(u1[:, :960, 3].astype(np.int16) + 18, 0, 235).astype(np.uint8)

    # Save Before/After visual comparison sheet
    canvas = Image.new('RGB', (1200, 760), (16, 18, 20))
    draw = ImageDraw.Draw(canvas)
    draw.text((14, 10), 'TEST 5 RES0001.BIN VISUAL VERIFICATION (LEFT: ORIGINAL | RIGHT: MODIFIED EMERALD)', fill=(240, 240, 240))

    panels = [
        ('NO INPUT + Orbit', render_rgba_rot90(arr0_orig[12131724:], 100, 177), render_rgba_rot90(arr0[12131724:], 100, 177), 30),
        ('MENU', render_rgba_rot90(arr0_orig[2937324:], 112, 112), render_rgba_rot90(arr0[2937324:], 112, 112), 155),
        ('REC Pills', render_rgba_rot90(arr0_orig[7806355:], 72, 216), render_rgba_rot90(arr0[7806355:], 72, 216), 290),
        ('Action Icons (w=48)', render_rgba_rot90(arr0_orig[12281244:], 48, 480), render_rgba_rot90(arr0[12281244:], 48, 480), 385),
        ('Input/Info Tabs (sample)', render_rgba_rot90(arr0_orig[14508085 + 96 * 7500:], 96, 1200), render_rgba_rot90(arr0[14508085 + 96 * 7500:], 96, 1200), 460),
    ]
    for title, im_b, im_a, y in panels:
        draw.text((14, y), title, fill=(140, 255, 170))
        canvas.paste(im_b, (210, y))
        canvas.paste(im_a, (710, y))

    draw.text((14, 580), 'Chunk 1 Wallpaper (1920x1080)', fill=(140, 255, 170))
    wp_b = yuv_to_rgb_img(u1_orig[:, :960, :]).resize((280, 157), Image.Resampling.BILINEAR)
    wp_a = yuv_to_rgb_img(u1[:, :960, :]).resize((280, 157), Image.Resampling.BILINEAR)
    canvas.paste(wp_b, (210, 580))
    canvas.paste(wp_a, (710, 580))
    os.makedirs(os.path.dirname(PREVIEW_PNG), exist_ok=True)
    canvas.save(PREVIEW_PNG)
    print(f'   Saved before/after preview -> {PREVIEW_PNG}')

    print('   Encoding modified Chunk 0 & Chunk 1 with PackBits-32...')
    new_c0_enc = encode_packbits32(bytes(d0_buf))
    new_c1_enc = encode_packbits32(bytes(d1_buf))
    assert decode_packbits32(new_c0_enc) == bytes(d0_buf), 'Chunk 0 PackBits-32 round-trip mismatch!'
    assert decode_packbits32(new_c1_enc) == bytes(d1_buf), 'Chunk 1 PackBits-32 round-trip mismatch!'

    struct.pack_into('<I', hdr0, 12, len(new_c0_enc))
    struct.pack_into('<I', hdr1, 12, len(new_c1_enc))
    new_res = bytes(hdr0) + new_c0_enc + bytes(hdr1) + new_c1_enc
    print(f'   RES0001.BIN sizes: orig={len(orig_res):,}, modified={len(new_res):,} (c0={len(new_c0_enc):,}, c1={len(new_c1_enc):,})')
    return new_res


def get_fat16_entry(img_path, target_name='RES0001.BIN'):
    with open(img_path, 'rb') as f:
        bpb = f.read(512)
        bps, spc, rsvd, nfats, nroot, _, _, spf = struct.unpack('<HBHBHHBH', bpb[11:24])
        fat_off = rsvd * bps
        root_off = (rsvd + nfats * spf) * bps
        data_off = root_off + nroot * 32
        clu_bytes = spc * bps

        f.seek(root_off)
        root_data = f.read(nroot * 32)
        dirent_off = None
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
                dirent_off = root_off + i * 32
                start_clu = struct.unpack('<H', ent[26:28])[0]
                fsize = struct.unpack('<I', ent[28:32])[0]
                break
        assert dirent_off is not None, f'{target_name} not found in FAT16!'

        f.seek(fat_off)
        fat_bytes = f.read(spf * bps)
        chain = []
        cur = start_clu
        while 2 <= cur < 0xFFF8:
            chain.append(cur)
            cur = struct.unpack('<H', fat_bytes[cur * 2:cur * 2 + 2])[0]
        return fat_off, nfats, spf * bps, clu_bytes, data_off, dirent_off, fsize, chain


def read_chain_bytes(img_path, clu_bytes, data_off, fsize, chain):
    buf = bytearray()
    with open(img_path, 'rb') as f:
        for clu in chain:
            f.seek(data_off + (clu - 2) * clu_bytes)
            buf.extend(f.read(clu_bytes))
    return bytes(buf[:fsize])


def write_fat16_file_same_or_shorter(img_path, fat_off, nfats, fat_bytes_len, clu_bytes, data_off, dirent_off, chain, payload):
    new_size = len(payload)
    max_cap = len(chain) * clu_bytes
    assert new_size <= max_cap, f'Modified file ({new_size}) exceeds existing cluster chain capacity ({max_cap})!'
    needed_clusters = (new_size + clu_bytes - 1) // clu_bytes
    used_chain = chain[:needed_clusters]
    unused_chain = chain[needed_clusters:]

    with open(img_path, 'r+b') as f:
        # 1. Write payload across needed clusters (zero pad remainder of last used cluster)
        pos = 0
        for clu in used_chain:
            chunk = payload[pos:pos + clu_bytes]
            if len(chunk) < clu_bytes:
                chunk = chunk + b'\x00' * (clu_bytes - len(chunk))
            f.seek(data_off + (clu - 2) * clu_bytes)
            f.write(chunk)
            pos += min(clu_bytes, new_size - pos)
        assert pos == new_size

        # 2. If fewer clusters are used, terminate chain cleanly & mark freed clusters 0x0000 in both FATs
        if unused_chain:
            last_used = used_chain[-1]
            for fi in range(nfats):
                base_fat = fat_off + fi * fat_bytes_len
                f.seek(base_fat + last_used * 2)
                f.write(struct.pack('<H', 0xFFFF))
                for free_c in unused_chain:
                    f.seek(base_fat + free_c * 2)
                    f.write(struct.pack('<H', 0x0000))

        # 3. Update directory entry file size (bytes 28..32)
        f.seek(dirent_off + 28)
        f.write(struct.pack('<I', new_size))
    return used_chain


def main():
    tmp_img = '/tmp/sec3_res_test5.img'
    tmp_gz = '/tmp/sec3_res_test5.bin.gz'
    tmp_sec3 = '/tmp/sec3_res_test5_aligned.bin'
    tmp_sec7 = '/tmp/sec7_res_test5.bin'

    print('1. Reading RES0001.BIN from clean stock sec3_decompressed.img...')
    fat_off, nfats, fat_len, clu_bytes, data_off, dirent_off, orig_sz_res, chain = get_fat16_entry(FAT_IMG_ORIG, 'RES0001.BIN')
    orig_res = read_chain_bytes(FAT_IMG_ORIG, clu_bytes, data_off, orig_sz_res, chain)
    print(f'   RES0001.BIN orig={orig_sz_res:,} B, clusters={len(chain)} (max={len(chain) * clu_bytes:,} B)')

    print('2. Building modified RES0001.BIN...')
    new_res = patch_res0001(orig_res)
    with open(OUT_RES_COPY, 'wb') as f:
        f.write(new_res)

    print('3. Copying clean sec3_decompressed.img -> /tmp/sec3_res_test5.img and updating RES0001.BIN...')
    shutil.copyfile(FAT_IMG_ORIG, tmp_img)
    used_chain = write_fat16_file_same_or_shorter(
        tmp_img, fat_off, nfats, fat_len, clu_bytes, data_off, dirent_off, chain, new_res
    )
    _, _, _, _, _, _, chk_sz, chk_chain = get_fat16_entry(tmp_img, 'RES0001.BIN')
    assert chk_sz == len(new_res) and chk_chain == used_chain
    with open(tmp_img, 'rb') as vf:
        vf.seek(fat_off)
        fat1_b = vf.read(fat_len)
        fat2_b = vf.read(fat_len)
        assert fat1_b == fat2_b, 'FAT1 != FAT2 mismatch!'
    chk_bytes = read_chain_bytes(tmp_img, clu_bytes, data_off, chk_sz, chk_chain)
    assert chk_bytes == new_res, 'FAT16 read-back mismatch for RES0001.BIN!'
    print(f'   FAT16 read-back & FAT1==FAT2 verified! ({len(chk_chain)} clusters used, {chk_sz:,} B)')

    # Extra verification: decode RES0001 read back from FAT16 image
    c0_len = struct.unpack('<I', chk_bytes[12:16])[0]
    d0_chk = decode_packbits32(chk_bytes[16:16 + c0_len])
    d1_chk = decode_packbits32(chk_bytes[16 + c0_len + 16:])
    assert len(d0_chk) == 80441908 and len(d1_chk) == 4423680
    print('   PackBits-32 decode check on FAT16 read-back RES0001.BIN passed!')

    print('4. Compressing /tmp/sec3_res_test5.img with gzip -n (level 6)...')
    with open(tmp_gz, 'wb') as out_gz:
        subprocess.run(['gzip', '-n', '-c', tmp_img], stdout=out_gz, check=True)
    gz_size = os.path.getsize(tmp_gz)
    target_sec3_size = 0x118C0000  # 294,387,712 bytes
    print(f'   gzip size={gz_size:,} B (limit={target_sec3_size - 4:,} B)')
    assert gz_size <= target_sec3_size - 4, f'gzip output too large: {gz_size} > {target_sec3_size - 4}'

    pad_len = target_sec3_size - 4 - gz_size
    with open(tmp_sec3, 'wb') as out_s3:
        with open(tmp_gz, 'rb') as in_gz:
            shutil.copyfileobj(in_gz, out_s3, length=1024 * 1024)
        out_s3.write(b'\xff' * pad_len)
        out_s3.write(b'\x00\x00\x14\xa7')
    assert os.path.getsize(tmp_sec3) == target_sec3_size

    sec3_crc = compute_section_crc(b'nibx', 0x30000000, 0x11111111, target_sec3_size, tmp_sec3, 0xFFFFFFFF)
    sec7_data = bytearray(open(os.path.join(SEC_DIR, 'sec7_idx_0x00013000.bin'), 'rb').read())
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

    sections = [
        ('sec0_bin_0xaaaaaaaa.bin', b' nib', 0x01000000, 0xaaaaaaaa, 1024, 0xe3421d1b, 0x00000000, os.path.join(SEC_DIR, 'sec0_bin_0xaaaaaaaa.bin')),
        ('sec1_bin_0xaaaaaaab.bin', b' nib', 0x01000000, 0xaaaaaaab, 1024, 0x9d9abe5f, 0x00000000, os.path.join(SEC_DIR, 'sec1_bin_0xaaaaaaab.bin')),
        ('sec2_bin_0xaaaaaaa2.bin', b' nib', 0x01000000, 0xaaaaaaa2, 1024, 0xa3650bb9, 0x00000000, os.path.join(SEC_DIR, 'sec2_bin_0xaaaaaaa2.bin')),
        ('sec3_res_test5.bin',      b'nibx', 0x30000000, 0x11111111, target_sec3_size, sec3_crc, 0xffffffff, tmp_sec3),
        ('sec4_xbin_0x31323334.bin', b'nibx', 0x30000000, 0x31323334, 2097152, 0x2182f35e, 0xffffffff, os.path.join(SEC_DIR, 'sec4_xbin_0x31323334.bin')),
        ('sec5_xbin_0x40404040.bin', b'nibx', 0x30000000, 0x40404040, 23068672, 0x9ed05ea0, 0xffffffff, os.path.join(SEC_DIR, 'sec5_xbin_0x40404040.bin')),
        ('sec6_bin_0xaaaaaaa1.bin', b' nib', 0x01000000, 0xaaaaaaa1, 1024, 0x200cee75, 0x00000000, os.path.join(SEC_DIR, 'sec6_bin_0xaaaaaaa1.bin')),
        ('sec7_res_test5.bin',      b' xdi', 0x01000000, 0x00013000, 192, sec7_crc, 0x00000000, tmp_sec7),
    ]

    os.makedirs(os.path.dirname(OUT_FW), exist_ok=True)
    global_hdr = struct.pack('<I4sII', 16, b'wfsa', 0x01000000, 8)
    with open(OUT_FW, 'wb') as out_f:
        out_f.write(global_hdr)
        for name, magic, ver, sid, pay_sz, crc, trl_val, path in sections:
            out_f.write(struct.pack('<I4sIIII', pay_sz + 28, magic, ver, sid, pay_sz, crc))
            with open(path, 'rb') as in_f:
                shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
            out_f.write(struct.pack('<I', trl_val))

    orig_sz = os.path.getsize(os.path.join(BASE_DIR, 'firmware', 'original', 'ATOMNJV.FW'))
    out_sz = os.path.getsize(OUT_FW)
    assert out_sz == orig_sz
    print(f'5. Built {OUT_FW} ({out_sz:,} B == original)')

    # Full 8-section CRC & structure audit
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
    print('ALL CHECKS PASSED FOR TEST #5!')


if __name__ == '__main__':
    main()

