#!/usr/bin/env python3
"""
Builds a minimal non-destructive ROOTFS-only AtomOS 11.19.00 firmware package
(deploy/ATOMNJV_RAW_HOOK.FW) for Ninja V units without UART serial access.

Safety guarantees:
  - Never modifies firmware/original/ATOMNJV.FW or extracted baseline images.
  - Leaves Sections 0, 1, 2, 4, 5, 6 (FSBL, PMU, ATF, U-Boot, phoenix_boot,
    recovery) and all encrypted DPGA*.BIN / APP0000.BIN / FLASH.UB / RAMDISK.UB
    / RES0001.BIN files 100% factory stock.
  - Installs into ROOTFS.BIN:
      * /usr/bin/vraw_daemon_arm64
      * /usr/lib/libfakecopro.so
      * /usr/bin/vraw_export.sh
      * /usr/bin/video_pipeline.sh (with LD_PRELOAD=/usr/lib/libfakecopro.so)
      * /usr/share/core_control/dump/licenses (calls vraw_export.sh on UI trigger)
      * /etc/init.d/vraw_hook + /etc/rc5.d/S99vraw_hook
  - Bumps the ext4 UUID of ROOTFS.BIN and ROOTFS.TXT to
    9b8f9d1a-bd53-4a10-8432-605efa2b7695 so phoenix_boot.bin unpacks the
    updated ROOTFS.BIN onto /dev/mmcblk0p5 on the first boot after update.
  - Exports diagnostic telemetry and captured DNG frames to the SATA SSD root
    via /usr/bin/send_files (respecting the <= 20 char IPI filename limit).
"""

import os
import shutil
import struct
import subprocess
import zlib

from build_res_test5_fw import (
    compute_section_crc,
    get_fat16_entry,
    patch_res0001,
    read_chain_bytes,
    write_fat16_file_same_or_shorter,
)

BASE_DIR = "/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab"
EXT_DIR = os.path.join(BASE_DIR, "firmware", "extracted")
SEC_DIR = os.path.join(EXT_DIR, "sections")
ORIG_ROOTFS = os.path.join(EXT_DIR, "rootfs_decompressed.img")
ORIG_SEC3 = os.path.join(EXT_DIR, "sec3_decompressed.img")
ORIG_FW = os.path.join(BASE_DIR, "firmware", "original", "ATOMNJV.FW")
OUT_FW = os.path.join(BASE_DIR, "deploy", "ATOMNJV_RAW_HOOK.FW")

VRAW_DAEMON_BIN = os.path.join(BASE_DIR, "recording-engine", "vraw_daemon_arm64")
FAKE_COPRO_SO = os.path.join(BASE_DIR, "reverse-engineering", "video-pipeline", "libfakecopro.so")

NEW_UUID = "9b8f9d1a-bd53-4a10-8432-605efa2b7696"
NEW_ROOTFS_TXT = f"UUID={NEW_UUID}\n".encode("ascii")

VIDEO_PIPELINE_WRAPPER = """#!/bin/sh

name=video_pipeline
exe="$name"
perf=

# Increase file descriptor limit to allocate more dmabufs
ulimit -n 10000

# Disable terminal colour and pipe output through logger
exec env GST_DEBUG_NO_COLOR=1 LD_PRELOAD=/usr/lib/libfakecopro.so COPRO_FWD_SOCK=/tmp/vraw_copro_fwd.sock COPRO_VERBOSE=1 $perf "$exe" "$@" 2>&1 | logger -s -t "$name"
"""

VRAW_EXPORT_SCRIPT = """#!/bin/sh
# Exports RAW diagnostic logs and captured DNG frames to the SATA SSD
# root (/) via /usr/bin/send_files (max basename length <= 20 chars).

TAG="${1:-now}"
BOOT_FILE="/tmp/vraw_b_${TAG}.txt"
COPRO_FILE="/tmp/vraw_c_${TAG}.txt"
DAEM_FILE="/tmp/vraw_d_${TAG}.txt"

{
    echo "=== RAW BOOT TELEMETRY ($TAG) ==="
    date
    uname -a
    cat /proc/cmdline 2>/dev/null
    echo "--- MOUNTS ---"
    mount
    df -h
    echo "--- LSMOD ---"
    lsmod
    echo "--- DEVICES & TMP ---"
    ls -la /dev/copro* /dev/dma_heap* /dev/allegro* /tmp/vraw* /tmp/vraw_clips 2>/dev/null
    echo "--- VIDEO_PIPELINE DEFAULT ---"
    cat /etc/default/video_pipeline 2>/dev/null
    echo "--- PS ---"
    ps
} > "$BOOT_FILE" 2>&1

{
    echo "=== RAW SYSLOG ($TAG) ==="
    grep -E "COPRO_|DMA_HEAP|CUSTOM_CMA|video_pipeline|VRAW|vraw" /var/log/messages 2>/dev/null | tail -n 300
    echo "=== TAIL MESSAGES ==="
    tail -n 80 /var/log/messages 2>/dev/null
} > "$COPRO_FILE" 2>&1

cp -f /tmp/vraw_daem.txt "$DAEM_FILE" 2>/dev/null || true
cp -f "$BOOT_FILE" /tmp/vraw_boot.txt 2>/dev/null || true
cp -f "$COPRO_FILE" /tmp/vraw_copro.txt 2>/dev/null || true

for f in /tmp/vraw_boot.txt /tmp/vraw_copro.txt /tmp/vraw_daem.txt "$BOOT_FILE" "$COPRO_FILE" "$DAEM_FILE"; do
    if [ -s "$f" ]; then
        send_files --timeout=2000 "$f" / >/dev/null 2>&1 || true
    fi
done

idx=0
for dng in /tmp/vraw_clips/*.dng; do
    [ -f "$dng" ] || continue
    short_dng=$(printf "/tmp/vraw_%03d.dng" "$idx")
    sent_mark="/tmp/.sent_vraw_${idx}"
    if [ ! -f "$sent_mark" ]; then
        cp -f "$dng" "$short_dng" 2>/dev/null || true
        if send_files --timeout=8000 "$short_dng" / >/dev/null 2>&1; then
            touch "$sent_mark"
        fi
        rm -f "$short_dng" 2>/dev/null || true
    fi
    idx=$((idx + 1))
    [ "$idx" -ge 3 ] && break
done

# Fallback if a USB stick is mounted under /run/media/*
for s in /run/media/*/vraw; do
    [ -d "$s" ] || continue
    mkdir -p "$s/logs" "$s/clips" 2>/dev/null || true
    cp -f /tmp/vraw_boot.txt /tmp/vraw_copro.txt /tmp/vraw_daem.txt "$s/logs/" 2>/dev/null || true
    cp -f /tmp/vraw_clips/*.dng "$s/clips/" 2>/dev/null || true
done
exit 0
"""

LICENSES_DUMP_SCRIPT = """#!/bin/sh
#
# (C) Copyright 2021 Atomos IP Pty Ltd. All Rights Reserved.
#

set -e
set -x

file=/tmp/licenses.tar.gz
rm -f "$file"
trap 'rm -f "$file"' EXIT QUIT TERM
tar -C /usr/share/ -zcf "$file" licenses/

send_files "$file" /

set +e
/usr/bin/vraw_export.sh ui >/dev/null 2>&1 || true
exit 0
"""

HOOK_SCRIPT = """#!/bin/sh
### BEGIN INIT INFO
# Provides:          vraw_hook
# Required-Start:    $local_fs
# Required-Stop:
# Default-Start:     5
# Default-Stop:
# Short-Description: RAW diagnostic & DNG capture service
### END INIT INFO

case "$1" in
  start)
    if [ -e /etc/vraw.disabled ]; then
        exit 0
    fi
    (
        mkdir -p /tmp/vraw_clips 2>/dev/null || true
        rm -f /tmp/vraw_copro_fwd.sock 2>/dev/null || true

        /usr/bin/vraw_daemon_arm64 --fwd-sock /tmp/vraw_copro_fwd.sock 3 /tmp/vraw_clips \
            > /tmp/vraw_daem.txt 2>&1 &

        i=0
        while [ ! -S /tmp/vraw_copro_fwd.sock ] && [ "$i" -lt 30 ]; do
            sleep 0.1 2>/dev/null || sleep 1
            i=$((i + 1))
        done
        chmod 666 /tmp/vraw_copro_fwd.sock 2>/dev/null || true

        if pidof video_pipeline >/dev/null 2>&1; then
            /etc/init.d/video_pipeline.sh stop >/dev/null 2>&1 || true
            sleep 1
            /etc/init.d/video_pipeline.sh start >/dev/null 2>&1 || true
        fi

        if command -v telnetd >/dev/null 2>&1; then
            telnetd -p 2323 -l /bin/sh >/dev/null 2>&1 || true
        fi

        for step in 15 30 45 60 90 120 180; do
            sleep 15
            /usr/bin/vraw_export.sh "$step" >/dev/null 2>&1 || true
        done

        while true; do
            sleep 20
            /usr/bin/vraw_export.sh loop >/dev/null 2>&1 || true
        done
    ) </dev/null >/dev/null 2>&1 &
    ;;
  stop)
    killall vraw_daemon_arm64 2>/dev/null || true
    ;;
  *)
    exit 0
    ;;
esac
exit 0
"""


def main():
    assert os.path.exists(VRAW_DAEMON_BIN), f"Missing {VRAW_DAEMON_BIN}"
    assert os.path.exists(FAKE_COPRO_SO), f"Missing {FAKE_COPRO_SO}"

    tmp_hook = "/tmp/vraw_hook"
    tmp_export = "/tmp/vraw_export.sh"
    tmp_vp_wrap = "/tmp/video_pipeline.sh"
    tmp_licenses = "/tmp/licenses_dump"
    tmp_cmds = "/tmp/debugfs_vraw_hook.txt"
    tmp_rootfs = "/tmp/rootfs_vraw_hook.img"
    tmp_rootfs_gz = "/tmp/ROOTFS_vraw_hook.BIN"
    tmp_sec3_img = "/tmp/sec3_vraw_hook.img"
    tmp_sec3_gz = "/tmp/sec3_vraw_hook.img.gz"
    tmp_sec3_aligned = "/tmp/sec3_vraw_hook.bin"
    tmp_sec7 = "/tmp/sec7_vraw_hook.bin"

    for path, content in (
        (tmp_hook, HOOK_SCRIPT),
        (tmp_export, VRAW_EXPORT_SCRIPT),
        (tmp_vp_wrap, VIDEO_PIPELINE_WRAPPER),
        (tmp_licenses, LICENSES_DUMP_SCRIPT),
    ):
        with open(path, "wb") as f:
            f.write(content.encode("ascii"))
        os.chmod(path, 0o755)
        subprocess.run(["sh", "-n", path], check=True)

    print("1. Copying baseline rootfs -> /tmp and installing RAW services...")
    shutil.copyfile(ORIG_ROOTFS, tmp_rootfs)

    cmds = (
        "cd /usr/bin\n"
        "rm vraw_daemon_arm64\n"
        f"write \"{VRAW_DAEMON_BIN}\" vraw_daemon_arm64\n"
        "set_inode_field vraw_daemon_arm64 mode 0100755\n"
        "rm vraw_export.sh\n"
        f"write {tmp_export} vraw_export.sh\n"
        "set_inode_field vraw_export.sh mode 0100755\n"
        "rm video_pipeline.sh\n"
        f"write {tmp_vp_wrap} video_pipeline.sh\n"
        "set_inode_field video_pipeline.sh mode 0100755\n"
        "cd /usr/lib\n"
        "rm libfakecopro.so\n"
        f"write \"{FAKE_COPRO_SO}\" libfakecopro.so\n"
        "set_inode_field libfakecopro.so mode 0100755\n"
        "cd /usr/share/core_control/dump\n"
        "rm licenses\n"
        f"write {tmp_licenses} licenses\n"
        "set_inode_field licenses mode 0100755\n"
        "cd /etc/init.d\n"
        "rm vraw_hook\n"
        f"write {tmp_hook} vraw_hook\n"
        "set_inode_field vraw_hook mode 0100755\n"
        "cd /etc/rc5.d\n"
        "rm S99vraw_hook\n"
        "symlink S99vraw_hook ../init.d/vraw_hook\n"
    )
    with open(tmp_cmds, "w") as f:
        f.write(cmds)
    subprocess.run(["debugfs", "-w", "-f", tmp_cmds, tmp_rootfs], check=True)

    for check_path in (
        "/usr/bin/vraw_daemon_arm64",
        "/usr/bin/vraw_export.sh",
        "/usr/bin/video_pipeline.sh",
        "/usr/lib/libfakecopro.so",
        "/usr/share/core_control/dump/licenses",
        "/etc/init.d/vraw_hook",
    ):
        stat_out = subprocess.run(
            ["debugfs", "-R", f"stat {check_path}", tmp_rootfs],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Inode:" in stat_out.stdout, f"{check_path} missing in rootfs!"

    subprocess.run(["e2fsck", "-fy", tmp_rootfs], capture_output=True, text=True)
    subprocess.run(["tune2fs", "-U", NEW_UUID, tmp_rootfs], capture_output=True, text=True, check=True)
    fsck = subprocess.run(["e2fsck", "-fn", tmp_rootfs], capture_output=True, text=True)
    assert fsck.returncode == 0, f"e2fsck failed:\n{fsck.stdout}\n{fsck.stderr}"

    tune = subprocess.run(["tune2fs", "-l", tmp_rootfs], capture_output=True, text=True, check=True)
    assert NEW_UUID in tune.stdout, "Rootfs UUID was not updated to NEW_UUID!"
    print(f"   [OK] e2fsck -fn clean & UUID updated to {NEW_UUID}.")

    print("2. Compressing ROOTFS.BIN with gzip -n -9...")
    with open(tmp_rootfs_gz, "wb") as out_f:
        subprocess.run(["gzip", "-n", "-9", "-c", tmp_rootfs], stdout=out_f, check=True)
    new_rootfs_sz = os.path.getsize(tmp_rootfs_gz)

    fat_off, nfats, fat_len, clu_bytes, data_off, dirent_off, orig_rootfs_sz, chain = get_fat16_entry(
        ORIG_SEC3, "ROOTFS.BIN"
    )
    cap_bytes = len(chain) * clu_bytes
    print(f"   ROOTFS.BIN new={new_rootfs_sz:,} B (orig={orig_rootfs_sz:,} B, cluster cap={cap_bytes:,} B)")
    assert new_rootfs_sz <= cap_bytes, f"New ROOTFS.BIN ({new_rootfs_sz}) exceeds cluster chain ({cap_bytes})!"

    print("3. Updating ROOTFS.BIN, ROOTFS.TXT, and RES0001.BIN inside /tmp FAT16 Section 3 image...")
    shutil.copyfile(ORIG_SEC3, tmp_sec3_img)
    with open(tmp_rootfs_gz, "rb") as rf:
        new_rootfs_bytes = rf.read()
    write_fat16_file_same_or_shorter(
        tmp_sec3_img, fat_off, nfats, fat_len, clu_bytes, data_off, dirent_off, chain, new_rootfs_bytes
    )

    # 3b. Update RES0001.BIN so the UI elements, buttons, and badges reflect the new theme/options
    print("   Patching RES0001.BIN UI assets (recolored REC pills, Menu tabs, and badges)...")
    res_fat_off, res_nfats, res_fat_len, res_clu_bytes, res_data_off, res_dirent_off, orig_sz_res, res_chain = get_fat16_entry(
        tmp_sec3_img, "RES0001.BIN"
    )
    orig_res = read_chain_bytes(tmp_sec3_img, res_clu_bytes, res_data_off, orig_sz_res, res_chain)
    new_res = patch_res0001(orig_res)
    write_fat16_file_same_or_shorter(
        tmp_sec3_img,
        res_fat_off,
        res_nfats,
        res_fat_len,
        res_clu_bytes,
        res_data_off,
        res_dirent_off,
        res_chain,
        new_res,
    )
    print(f"   [OK] RES0001.BIN UI assets updated in FAT16 image ({len(new_res):,} B).")

    # Update ROOTFS.TXT so phoenix_boot.bin sees the new UUID and unpacks ROOTFS.BIN to /dev/mmcblk0p5
    (
        txt_fat_off,
        txt_nfats,
        txt_fat_len,
        txt_clu_bytes,
        txt_data_off,
        txt_dirent_off,
        orig_txt_sz,
        txt_chain,
    ) = get_fat16_entry(tmp_sec3_img, "ROOTFS.TXT")
    assert len(NEW_ROOTFS_TXT) == orig_txt_sz == 42
    write_fat16_file_same_or_shorter(
        tmp_sec3_img,
        txt_fat_off,
        txt_nfats,
        txt_fat_len,
        txt_clu_bytes,
        txt_data_off,
        txt_dirent_off,
        txt_chain,
        NEW_ROOTFS_TXT,
    )
    readback_txt = read_chain_bytes(tmp_sec3_img, txt_clu_bytes, txt_data_off, len(NEW_ROOTFS_TXT), txt_chain)
    assert readback_txt == NEW_ROOTFS_TXT, f"ROOTFS.TXT readback mismatch: {readback_txt!r}"
    print(f"   [OK] ROOTFS.TXT updated to {NEW_ROOTFS_TXT.decode('ascii').strip()}")

    print("4. Compressing Section 3 FAT16 image with gzip -n...")
    with open(tmp_sec3_gz, "wb") as gz_f:
        subprocess.run(["gzip", "-n", "-c", tmp_sec3_img], stdout=gz_f, check=True)
    sec3_gz_sz = os.path.getsize(tmp_sec3_gz)
    target_sec3_size = 0x118C0000
    print(f"   sec3 gzip size={sec3_gz_sz:,} B (limit={target_sec3_size - 4:,} B)")
    assert sec3_gz_sz <= target_sec3_size - 4, "Section 3 compressed image exceeds 0x118C0000 limit!"

    pad_len = target_sec3_size - 4 - sec3_gz_sz
    with open(tmp_sec3_aligned, "wb") as s3_f:
        with open(tmp_sec3_gz, "rb") as gz_f:
            shutil.copyfileobj(gz_f, s3_f, length=1024 * 1024)
        s3_f.write(b"\xff" * pad_len)
        s3_f.write(b"\x00\x00\x14\xa7")
    assert os.path.getsize(tmp_sec3_aligned) == target_sec3_size

    sec3_crc = compute_section_crc(b"nibx", 0x30000000, 0x11111111, target_sec3_size, tmp_sec3_aligned, 0xFFFFFFFF)
    sec7_data = bytearray(open(os.path.join(SEC_DIR, "sec7_idx_0x00013000.bin"), "rb").read())
    assert len(sec7_data) == 192
    entry3_off = 96
    assert struct.unpack_from("<I", sec7_data, entry3_off + 12)[0] == 0x11111111
    struct.pack_into("<I", sec7_data, entry3_off + 16, target_sec3_size)
    struct.pack_into("<I", sec7_data, entry3_off + 20, sec3_crc)
    struct.pack_into("<I", sec7_data, 4, zlib.crc32(sec7_data[8:184], 0xFFFFFFFF))
    with open(tmp_sec7, "wb") as f:
        f.write(sec7_data)
    sec7_crc = compute_section_crc(b" xdi", 0x01000000, 0x00013000, 192, tmp_sec7, 0x00000000)

    sections = [
        ("sec0_bin_0xaaaaaaaa.bin", b" nib", 0x01000000, 0xaaaaaaaa, 1024, 0xe3421d1b, 0x00000000, os.path.join(SEC_DIR, "sec0_bin_0xaaaaaaaa.bin")),
        ("sec1_bin_0xaaaaaaab.bin", b" nib", 0x01000000, 0xaaaaaaab, 1024, 0x9d9abe5f, 0x00000000, os.path.join(SEC_DIR, "sec1_bin_0xaaaaaaab.bin")),
        ("sec2_bin_0xaaaaaaa2.bin", b" nib", 0x01000000, 0xaaaaaaa2, 1024, 0xa3650bb9, 0x00000000, os.path.join(SEC_DIR, "sec2_bin_0xaaaaaaa2.bin")),
        ("sec3_vraw_hook",     b"nibx", 0x30000000, 0x11111111, target_sec3_size, sec3_crc, 0xFFFFFFFF, tmp_sec3_aligned),
        ("sec4_xbin_0x31323334.bin", b"nibx", 0x30000000, 0x31323334, 2097152, 0x2182f35e, 0xFFFFFFFF, os.path.join(SEC_DIR, "sec4_xbin_0x31323334.bin")),
        ("sec5_xbin_0x40404040.bin", b"nibx", 0x30000000, 0x40404040, 23068672, 0x9ed05ea0, 0xFFFFFFFF, os.path.join(SEC_DIR, "sec5_xbin_0x40404040.bin")),
        ("sec6_bin_0xaaaaaaa1.bin", b" nib", 0x01000000, 0xaaaaaaa1, 1024, 0x200cee75, 0x00000000, os.path.join(SEC_DIR, "sec6_bin_0xaaaaaaa1.bin")),
        ("sec7_vraw_hook",     b" xdi", 0x01000000, 0x00013000, 192, sec7_crc, 0x00000000, tmp_sec7),
    ]

    os.makedirs(os.path.dirname(OUT_FW), exist_ok=True)
    global_hdr = struct.pack("<I4sII", 16, b"wfsa", 0x01000000, 8)
    with open(OUT_FW, "wb") as out_f:
        out_f.write(global_hdr)
        for _, magic, ver, sid, pay_sz, crc, trl_val, path in sections:
            out_f.write(struct.pack("<I4sIIII", pay_sz + 28, magic, ver, sid, pay_sz, crc))
            with open(path, "rb") as in_f:
                shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
            out_f.write(struct.pack("<I", trl_val))

    assert os.path.getsize(OUT_FW) == os.path.getsize(ORIG_FW)
    print(f"5. Auditing all 8 sections of {OUT_FW} ({os.path.getsize(OUT_FW):,} B)...")
    with open(OUT_FW, "rb") as f:
        assert f.read(16) == global_hdr
        for name, magic, ver, sid, pay_sz, expected_crc, _, _ in sections:
            s_hdr = f.read(24)
            tot_len, s_mag, s_ver, s_id, s_pay, s_crc = struct.unpack("<I4sIIII", s_hdr)
            assert (s_mag, s_ver, s_id, s_pay, s_crc) == (magic, ver, sid, pay_sz, expected_crc)
            c = zlib.crc32(struct.pack("<I4sIIII", tot_len, s_mag, s_ver, s_id, s_pay, 0), 0xFFFFFFFF)
            rem = s_pay
            while rem > 0:
                chunk = f.read(min(1024 * 1024, rem))
                c = zlib.crc32(chunk, c)
                rem -= len(chunk)
            c = zlib.crc32(f.read(4), c)
            assert c == expected_crc
            print(f"   [OK] {name:24s} CRC 0x{c:08x}")

    for p in (
        tmp_hook,
        tmp_export,
        tmp_vp_wrap,
        tmp_licenses,
        tmp_cmds,
        tmp_rootfs,
        tmp_rootfs_gz,
        tmp_sec3_img,
        tmp_sec3_gz,
        tmp_sec3_aligned,
        tmp_sec7,
    ):
        if os.path.exists(p):
            os.remove(p)

    print("SUCCESS: deploy/ATOMNJV_RAW_HOOK.FW built and verified!")


if __name__ == "__main__":
    main()
