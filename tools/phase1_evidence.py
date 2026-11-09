"""Phase 1 evidence collector (read-only).

Reads extracted firmware files and writes measured facts to
reverse-engineering/evidence/phase1_evidence.json. Every number in the
Phase 1 reports must come from this file. Never writes to firmware/original.
"""
import hashlib, json, math, os, re, struct

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
X = os.path.join(R, "firmware", "extracted")
FAT = os.path.join(X, "fat16_fs")
ROOT = os.path.join(X, "rootfs_ext4")
OUT = os.path.join(R, "reverse-engineering", "evidence")


def rd(p):
    with open(p, "rb") as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def entropy(b):
    if not b:
        return 0.0
    n = len(b)
    return round(-sum((c / n) * math.log2(c / n) for c in (b.count(i) for i in range(256)) if c), 6)


def boot_image(path):
    """Record raw Xilinx boot-image header fields. No interpretation of crypto flags."""
    b = rd(path)
    info = {"file": os.path.relpath(path, R).replace("\\", "/"), "size": len(b), "sha256": sha(b)}
    if b[0x24:0x28] != b"XNLX":  # 0x584C4E58 ("XLNX") stored little-endian
        info["xlnx_magic"] = False
        return info
    info["xlnx_magic"] = True
    info["width_detect"] = hex(struct.unpack_from("<I", b, 0x20)[0])
    info["key_source_raw"] = hex(struct.unpack_from("<I", b, 0x28)[0])
    info["fsbl_exec_addr"] = hex(struct.unpack_from("<I", b, 0x2C)[0])
    iht = struct.unpack_from("<I", b, 0x98)[0]
    info["image_header_table_offset"] = hex(iht)
    ver, count, ph_off_w, ih_off_w = struct.unpack_from("<IIII", b, iht)
    info["iht_version"] = hex(ver)
    info["image_count"] = count
    # image names
    names = []
    off = ih_off_w * 4
    seen = set()
    while off and off < len(b) and off not in seen and len(names) < 64:
        seen.add(off)
        nxt_w, ph_w = struct.unpack_from("<II", b, off)[:2]
        raw = b[off + 16: off + 16 + 256]
        # name is stored as big-endian 32-bit words
        chars = bytearray()
        for i in range(0, len(raw), 4):
            w = raw[i:i + 4][::-1]
            if b"\x00" in w:
                chars += w.split(b"\x00")[0]
                break
            chars += w
        names.append(chars.decode("latin1"))
        off = nxt_w * 4
    info["image_names"] = names
    parts = []
    off = ph_off_w * 4
    seen = set()
    while off and off + 64 <= len(b) and off not in seen and len(parts) < 64:
        seen.add(off)
        w = struct.unpack_from("<16I", b, off)
        data_off = w[8] * 4
        tot = w[2] * 4
        payload = b[data_off:data_off + min(tot, 1 << 20)]
        parts.append({
            "header_offset": hex(off),
            "enc_len_words": w[0], "unenc_len_words": w[1], "total_len_words": w[2],
            "exec_addr": hex(w[4] | (w[5] << 32)), "load_addr": hex(w[6] | (w[7] << 32)),
            "data_offset": hex(data_off), "attributes_raw": hex(w[9]),
            "dest_cpu_field": (w[9] >> 8) & 0xF, "dest_device_field": (w[9] >> 4) & 0x7,
            "payload_first16": payload[:16].hex(),
            "payload_has_elf_magic": payload[:4] == b"\x7fELF",
            "payload_has_fpga_sync_word_first1MiB": b"\xaa\x99\x55\x66" in payload,
            "payload_entropy_first1MiB": entropy(payload),
        })
        off = w[3] * 4
    info["partitions"] = parts
    return info


ev = {}

# FAT16 file list (measured)
ev["fat16_files"] = []
for n in sorted(os.listdir(FAT)):
    b = rd(os.path.join(FAT, n))
    ev["fat16_files"].append({"name": n, "size": len(b), "sha256": sha(b),
                              "first16": b[:16].hex(), "entropy": entropy(b)})

# Boot-image style files
targets = [os.path.join(X, "sections", "sec4_xbin_0x31323334.bin"),
           os.path.join(X, "sections", "sec5_xbin_0x40404040.bin")]
targets += [os.path.join(FAT, n) for n in sorted(os.listdir(FAT))
            if rd(os.path.join(FAT, n))[0x24:0x28] == b"XNLX"]
ev["boot_images"] = [boot_image(t) for t in targets]

# Plain text files
for n in ["MANIFEST.XMD", "ROOTFS.TXT"]:
    ev.setdefault("text_files", {})[n] = rd(os.path.join(FAT, n)).decode("latin1")

# Plain Xilinx .bit headers (FMOD*)
ev["bit_headers"] = {}
for n in ["FMODDOCK.BIN", "FMODSTRM.BIN"]:
    b = rd(os.path.join(FAT, n))
    fields = re.findall(rb"[\x20-\x7e]{6,}", b[:256])
    ev["bit_headers"][n] = [f.decode() for f in fields]

# SVF headers
ev["svf_headers"] = {}
for n in ["XMODDOCK.BIN", "XMODSTRM.BIN", "XMODSDI.BIN", "XMODSYN.BIN"]:
    ev["svf_headers"][n] = rd(os.path.join(FAT, n))[:600].decode("latin1").splitlines()[:12]

# Kernel banner
img = rd(os.path.join(X, "fit_flash_ub", "Image"))
m = re.search(rb"Linux version [\x20-\x7e]+", img)
ev["kernel_banner"] = m.group(0).decode() if m else None

# Rootfs config files
ev["rootfs_files"] = {}
for n in ["etc/fstab", "etc/inittab", "etc/version", "etc/hostname", "etc/issue"]:
    p = os.path.join(ROOT, n)
    ev["rootfs_files"][n] = rd(p).decode("latin1") if os.path.exists(p) else None
for n in ["etc/os-release", "usr/lib/os-release"]:
    p = os.path.join(ROOT, n)
    ev["rootfs_files"][n] = rd(p).decode("latin1") if os.path.exists(p) else None

# init scripts for Atomos services (full text)
ev["init_scripts"] = {}
for n in ["video_pipeline.sh", "streaming_pl.sh", "core_control.sh", "cloud_service.sh",
          "media_control.sh", "camera_control.sh", "audio_encoder.sh", "talkback_pl.sh",
          "partition-migrate.sh", "phoenix-diagnostics.sh", "modutils.sh", "rcS"]:
    p = os.path.join(ROOT, "etc", "init.d", n)
    if os.path.exists(p):
        ev["init_scripts"][n] = rd(p).decode("latin1")
ev["rc5_links"] = sorted(os.listdir(os.path.join(ROOT, "etc", "rc5.d")))
rcs = os.path.join(ROOT, "etc", "rcS.d")
ev["rcS_links"] = sorted(os.listdir(rcs)) if os.path.isdir(rcs) else None
mods = os.path.join(ROOT, "etc", "modules-load.d")
ev["modules_load"] = {n: rd(os.path.join(mods, n)).decode("latin1") for n in os.listdir(mods)} if os.path.isdir(mods) else None

# Atomos service binaries: size, hash, ELF fields, DT_NEEDED, keyword hits
KEYWORDS = [b"copro_comms", b"copro_buf", b"/dev/", b"prores", b"ProRes", b"dnx", b"DNx", b"raw", b"RAW",
            b"bayer", b"Bayer", b"12bit", b"nv12", b"nv16", b"XV20", b"omxh265enc", b"omxh264enc",
            b"qtmux", b"mp4mux", b"matroskamux", b"ndi", b"srt", b"rtmp", b"/sys/", b"fpga", b"DPGA"]


def elf_info(b):
    if b[:4] != b"\x7fELF":
        return None
    e_machine = struct.unpack_from("<H", b, 18)[0]
    shoff = struct.unpack_from("<Q", b, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", b, 0x3A)
    secs = []
    for i in range(shnum):
        s = struct.unpack_from("<IIQQQQIIQQ", b, shoff + i * shentsize)
        secs.append(s)
    needed, stripped = [], True
    names_off = secs[shstrndx][4] if shnum else 0
    def sname(s):
        o = names_off + s[0]
        return b[o:b.index(b"\x00", o)].decode()
    dyn = dynstr = None
    for s in secs:
        nm = sname(s)
        if nm == ".symtab":
            stripped = False
        if nm == ".dynamic":
            dyn = s
        if nm == ".dynstr":
            dynstr = s
    if dyn and dynstr:
        for i in range(0, dyn[5], 16):
            tag, val = struct.unpack_from("<qQ", b, dyn[4] + i)
            if tag == 0:
                break
            if tag == 1:
                o = dynstr[4] + val
                needed.append(b[o:b.index(b"\x00", o)].decode())
    return {"e_machine": e_machine, "has_symtab": not stripped, "needed": needed}


ev["services"] = {}
for n in ["video_pipeline", "streaming_pl", "core_control", "cloud_service", "media_control",
          "camera_control", "audio_encoder", "talkback_pl", "ctrlsw_encoder", "ctrlsw_decoder"]:
    p = os.path.join(ROOT, "usr", "bin", n)
    b = rd(p)
    strs = set(s.decode() for s in re.findall(rb"[\x20-\x7e]{5,}", b))
    hits = {}
    for k in KEYWORDS:
        ks = k.decode()
        found = sorted(s for s in strs if ks in s)
        if found:
            hits[ks] = found[:25]
    ev["services"][n] = {"size": len(b), "sha256": sha(b), "elf": elf_info(b), "keyword_strings": hits}

# custom kernel modules
ev["custom_modules"] = {}
md = os.path.join(ROOT, "lib", "modules", "6.1.5-xilinx-v2023.1", "extra")
for dp, _, fs in os.walk(md):
    for f in fs:
        if f.endswith(".ko"):
            b = rd(os.path.join(dp, f))
            mi = sorted(set(s.decode() for s in re.findall(rb"(?:description|author|license|version|vermagic|alias)=[\x20-\x7e]+", b)))
            ev["custom_modules"][f] = {"size": len(b), "sha256": sha(b), "modinfo": mi}

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "phase1_evidence.json"), "w", encoding="utf-8") as f:
    json.dump(ev, f, indent=2)
print("ok", len(ev["fat16_files"]), "fat files;", len(ev["boot_images"]), "boot images")

