# Phase 1 Deliverable: Firmware Container & Bootloader Reverse Engineering Report (`ATOMNJV.FW` — AtomOS 11.19.00)

- **Project:** Verdanove Ninja Lab
- **Target Device:** Original Atomos Ninja V (5-inch model)
- **Firmware File:** `firmware/original/ATOMNJV.FW` (`319,558,064` bytes / `0x130c11b0` bytes)
- **Firmware Version:** AtomOS `11.19.00` (Internal Build `99.99.99-7121` / `11.19.00` release package)
- **SHA-256 (`ATOMNJV.FW`):** `65e14e67bcc2624115300624d967634042601f23e9574e75ee7f06f2c8004be1`
- **Original File Integrity:** Verified `OK` against `SHA256SUMS`; `IsReadOnly = True` enforced.

---

## 1. Executive Summary

Non-destructive static reverse engineering of `ATOMNJV.FW` (AtomOS 11.19.00) revealed the complete outer container specification, embedded Xilinx Zynq UltraScale+ (`XCZU5EV`) QSPI boot images, FAT16 firmware staging repository, U-Boot FIT images (`FLASH.UB`, `RAMDISK.UB`), decompressed Linux 6.1.5 kernel, device tree (`system.dtb`), initramfs (`ramdisk.cpio`), and production `ext4` root filesystem (`ROOTFS.BIN`).

Crucially, comparing our empirical findings against the community analysis of AtomOS 10.94.01 (`v3ntus`) uncovered several major architectural truths and corrections:
1. **Outer Container (`wfsa` / `"asfw"`):** The firmware file is a structured 8-section container with a 16-byte global header, 24-byte section headers, and 4-byte trailers, terminated by a 192-byte Section 7 (`idx `) directory table.
2. **Xilinx ZynqMP Boot Images (`sec4` & `sec5`) and Selective AES-GCM eFUSE Encryption:**
   - The Linux kernel (`FLASH.UB`), device tree (`system.dtb`), initramfs (`RAMDISK.UB`), `ext4` root filesystem (`ROOTFS.BIN`), U-Boot (`u-boot.elf`), and expansion module bitstreams (`FMODDOCK.BIN`, `FMODSTRM.BIN`, `XMOD*.BIN`) are **completely unencrypted**.
   - However, the first-stage bootloaders (`phoenix_fsbl.elf`, `phoenix_pmu.elf`, `bl31.elf`, `phoenix_boot.bin`), the Cortex-R5 real-time application (`APP0000.BIN` / `DAPP0000.BIN` -> `startrek_noresources.elf`), and all 16 ZynqMP Programmable Logic (PL) FPGA bitstreams (`DPGA0000.BIN`–`DPGA0020.BIN` and `emergency.bit`) have ZynqMP Partition Header attribute bit 7 (`0x80`) set and Boot Header Key Source `0xA5C3C5A3` (`EFUSE_RED_KEY`), proving they are **AES-GCM-256 encrypted using a hardware key fused into the ZynqMP eFUSE**.

---

## 2. Outer Firmware Container Format (`wfsa` / `"asfw"`)

### 2.1 Global Container Header (`0x00000000`–`0x0000000F`, 16 bytes)

| Offset | Size | Type | Value (Hex / ASCII) | Description |
|---|---|---|---|---|
| `0x00` | 4 B | `uint32_le` | `0x00000010` (16) | Global header size in bytes |
| `0x04` | 4 B | `char[4]` | `77 66 73 61` (`"wfsa"`) | Container magic (little-endian for `"asfw"`, Atomos System Firmware) |
| `0x08` | 4 B | `uint32_le` | `0x01000000` | Format version |
| `0x0C` | 4 B | `uint32_le` | `0x00000008` (8) | Number of sections (`num_sections = 8`) |

### 2.2 Per-Section Framing (`24-byte Header + Payload + 4-byte Trailer`)

Every section begins with a 24-byte (`0x18`) header (`struct.unpack('<I4sIIII', hdr)`), followed by `payload_len` bytes of raw data, followed by a 4-byte (`0x04`) trailer (`total_len = payload_len + 0x1C`):

| Field Offset | Size | Field Name | Description |
|---|---|---|---|
| `+0x00` | 4 B | `total_len` | Total section span in bytes (`payload_len + 0x1C`) |
| `+0x04` | 4 B | `magic` | Section type: `"bin "` (RAM/zero placeholder), `"xbin"` (flashable binary payload), or `"idx "` (container index table) |
| `+0x08` | 4 B | `version` | Always `0x00000001` |
| `+0x0C` | 4 B | `section_id` | Target storage/partition identifier (`0x11111111`, `0x31323334`, `0x40404040`, etc.) |
| `+0x10` | 4 B | `payload_len` | Exact payload length in bytes |
| `+0x14` | 4 B | `hdr_crc` | 32-bit checksum over the section header |
| `+0x18 + payload_len` | 4 B | `trailer` | `0x00000000` for `"bin "` / `"idx "`, `0xFFFFFFFF` for `"xbin"` |

### 2.3 Complete Section Table of `ATOMNJV.FW`

| Sec # | Header Offset | Payload Offset | Magic | Section ID | Payload Size (Bytes) | Trailer | Payload SHA-256 | Role & Contents |
|---|---|---|---|---|---|---|---:|---|
| **0** | `0x00000010` | `0x00000028` | `"bin "` | `0xaaaaaaaa` | `1,024` (`0x400`) | `0x00000000` | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7` | 1 KiB all-zero placeholder |
| **1** | `0x0000042c` | `0x00000444` | `"bin "` | `0xaaaaaaab` | `1,024` (`0x400`) | `0x00000000` | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7` | 1 KiB all-zero placeholder |
| **2** | `0x00000848` | `0x00000860` | `"bin "` | `0xaaaaaaa2` | `1,024` (`0x400`) | `0x00000000` | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7` | 1 KiB all-zero placeholder |
| **3** | `0x00000c64` | `0x00000c7c` | `"xbin"` | `0x11111111` | `294,387,712` (`0x118c0000`) | `0xffffffff` | `204628d18203c8689d00fd79f1d09e691483051cdbd986de04f293c31d87f352` | GZIP-compressed FAT16 image (`293,502,944` B GZIP stream + `884,768` B `0xFF` flash padding) |
| **4** | `0x118c0c80` | `0x118c0c98` | `"xbin"` | `0x31323334` (`"4321"`) | `2,097,152` (`0x00200000`) | `0xffffffff` | `3da795655b306278081e2c5df52dfca0432d9c30689d3f5a5fa8d54c860f8f7f` | Primary 2 MiB QSPI `BOOT.BIN` (ZynqMP FSBL, PMUFW, ATF BL31, `boot.dtb`, `phoenix_boot.bin`, `u-boot.elf`) |
| **5** | `0x11ac0c9c` | `0x11ac0cb4` | `"xbin"` | `0x40404040` (`"@@@@"`) | `23,068,672` (`0x01600000`) | `0xffffffff` | `370252160079c63f802d0795f61658ed0214807f34e386673d3d4a5a4e686bc6` | Recovery/Golden 22 MiB QSPI `BOOT.BIN` (adds `emergency.bit`, `system.dtb`, `Image.gz`, `rootfs.cpio.gz.u-boot`) |
| **6** | `0x130c0cb8` | `0x130c0cd0` | `"bin "` | `0xaaaaaaa1` | `1,024` (`0x400`) | `0x00000000` | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7` | 1 KiB all-zero placeholder |
| **7** | `0x130c10d4` | `0x130c10ec` | `"idx "` | `0x00013000` | `192` (`0x00c0`) | `0x00000000` | `e98702be8f6027b0cb73bc70698026f73ee27e8d801f536fb09fb99787d311bf` | Master Container Index Table (16 B copy of global header + seven 24 B section header descriptors) |

---

## 3. Bootloader & ZynqMP `BOOT.BIN` Partition Analysis (`sec4` & `sec5`)

Both `sec4` (`2,097,152` bytes) and `sec5` (`23,068,672` bytes) carry valid Xilinx Zynq UltraScale+ Boot Headers (`XLNX` magic at `+0x24`, image header table at `0x000008C0`, first partition header at `0x00000AC0`).

### 3.1 Boot Header Security Attributes
- **Key Source (`+0x28`):** `0xA5C3C5A3` — Xilinx ZynqMP hardware constant for **`EFUSE_RED_KEY`** (AES-GCM-256 key stored in on-SoC eFUSE).
- **FSBL Execution Address (`+0x2C`):** `0xFFFC0000` (ZynqMP On-Chip Memory / OCM).

### 3.2 `sec4_xbin_0x31323334.bin` (Primary 2 MiB QSPI Boot Image)

| Part # | Image Name (`ImageHeader`) | Data Offset | Data Size (B) | Load Address | Exec Address | Dest Dev | Encrypted? | Description |
|---|---|---:|---:|---|---|---|---|---|
| **0** | `phoenix_fsbl.elf` | `0x00001740` | `135,168` | `0xFFFC0000` | `0xFFFC0000` | A53-0 | **YES (`EFUSE_RED_KEY`)** | First Stage Bootloader in OCM |
| **1** | `phoenix_pmu.elf` | `0x00022740` | `124,992` | `0xFFDC0000` | `0xFFDDDF94` | PMU | **YES (`EFUSE_RED_KEY`)** | Platform Management Unit MicroBlaze FW |
| **2** | `bl31.elf` | `0x00040F80` | `49,408` | `0xFFFEA000` | `0xFFFEA000` | A53-0 (EL3) | **YES (`EFUSE_RED_KEY`)** | ARM Trusted Firmware (ATF BL31) |
| **3** | `boot.dtb` | `0x0004D080` | `30,000` | `0x00100000` | `0x00000000` | Memory | **NO** (`0xd00dfeed`) | U-Boot Flattened Device Tree (`xlnx,zynqmp`) |
| **4** | `phoenix_boot.bin` | `0x000545C0` | `642,496` | `0x0C100000` | `0x0C100000` | A53-0 | **YES (`EFUSE_RED_KEY`)** | Atomos custom pre-OS bootloader / updater |
| **5** | `u-boot.elf` | `0x000F1380` | `848,160` | `0x08000000` | `0x08000000` | A53-0 (EL2) | **NO** | `U-Boot 2023.01 (Nov 15 2023 - 09:05:49 +0000)` |

### 3.3 `sec5_xbin_0x40404040.bin` (Recovery / Golden 22 MiB QSPI Boot Image)

| Part # | Image Name (`ImageHeader`) | Data Offset | Data Size (B) | Load Address | Exec Address | Dest Dev | Encrypted? | Description |
|---|---|---:|---:|---|---|---|---|---|
| **0–5** | Same as `sec4` (`phoenix_fsbl` .. `u-boot.elf`) | `0x00001740` | — | — | — | — | Same as `sec4` | Identical boot chain |
| **6** | `emergency.bit` | `0x001C04C0` | `5,568,448` | `0xFFFFFFFF` | `0x00000000` | PL (FPGA) | **YES (`EFUSE_RED_KEY`)** | Golden recovery FPGA bitstream |
| **7** | `system.dtb` | `0x0070FC00` | `30,000` | `0x08000000` | `0x00000000` | Memory | **NO** (`0xd00dfeed`) | Recovery Device Tree Blob |
| **8** | `Image.gz` | `0x00717140` | `7,942,100` | `0x08080000` | `0x00000000` | Memory | **NO** (GZIP `1f 8b`) | Compressed Linux 6.1.5 Kernel |
| **9** | `rootfs.cpio.gz.u-boot` | `0x00EAA140` | `7,232,124` | `0x0A000000` | `0x00000000` | Memory | **NO** (U-Boot `27 05 19 56`) | Legacy recovery ramdisk (`ramdisk.cpio.gz`) |

### 3.4 U-Boot Environment & Boot Sequence (`u-boot.elf`)
Extracted directly from `u-boot.elf` (`U-Boot 2023.01`):
- `bootcmd=run flashboot`
- `flashboot=echo Booting normal system from FLASH...; fpga load 0 ${loadbit_addr} ${filesize}; bootm ${flash_ub_addr} ${ramdisk_ub_addr}`
  - Note: in `u-boot.elf`, normal boot reads `FLASH.UB` (kernel + `system.dtb`) and `RAMDISK.UB` (initramfs), which then runs `/init` to mount the eMMC `ext4` root filesystem (`ROOTFS.BIN`) and start the Cortex-R5 processor.
- `recboot=echo Booting into recovery image...; bootm 0x8080000 0xA000000 0x8000000` (boots the embedded `sec5` recovery kernel, ramdisk, and `system.dtb`).

---

## 4. Kernel & Device Tree Identification (`FLASH.UB` & `RAMDISK.UB`)

### 4.1 `FLASH.UB` (`8,225,532` bytes) — U-Boot FIT Image (`conf-system.dtb`)
- **`kernel-1` (`8,193,971` bytes, GZIP):** Decompresses to `22,813,184` bytes (`0x015c1a00`), load/entry address `0x00200000`.
  - **Kernel Version Banner:**
    `Linux version 6.1.5-xilinx-v2023.1 (oe-user@oe-host) (aarch64-xilinx-linux-gcc (GCC) 12.2.0, GNU ld (GNU Binutils) 2.39.0.20220819) #1 SMP Fri Nov 10 04:40:28 UTC 2023`
- **`fdt-system.dtb` (`29,995` bytes):**
  - Root properties: `model = "Atomos NinjaV"`, `compatible = "atms,ninjav", "xlnx,zynqmp"`.

### 4.2 `RAMDISK.UB` (`36,204,196` bytes) — U-Boot FIT Image (`ramdisk-1`)
- **`ramdisk-1` (`36,203,149` bytes, GZIP):** Decompresses to `ramdisk.cpio` (`122,461,184` bytes / `116.79 MiB`, SVR4 `newc` CPIO archive containing `1,677` entries).
- Its `/init` script mounts `/proc`, `/sys`, `/dev`, checks `/proc/cmdline` (`recovery` vs normal boot), mounts the eMMC root partition (`/dev/mmcblk0p2`) at `/newroot`, and `switch_root`s into the production `ext4` filesystem (`ROOTFS.BIN`).

---

## 5. Comparison with Community Analysis (AtomOS 10.94.01 vs. AtomOS 11.19.00)

The community blog post by `v3ntus` (*Atomos Reverse Engineering*, analyzing AtomOS `10.94.01`) provided useful initial hints, but our static inspection of AtomOS `11.19.00` corrected and expanded several critical points:

| Topic | Community Report (AtomOS 10.94.01 / `v3ntus`) | Verified Findings in AtomOS 11.19.00 (`ATOMNJV.FW`) | Impact on Project |
|---|---|---|---|
| **SoC Part Number** | Generic "Zynq UltraScale+ MPSoC" | **Xilinx Zynq UltraScale+ `XCZU5EV`** (verified via Yocto module build path `atomos_ninjav_xczu5ev-xilinx-linux` and `system.dtb`) | Confirms EV-series SoC with hardware H.264/H.265 VCU and 4x Cortex-A53 + 2x Cortex-R5 |
| **APU CPU Cores** | Claimed "Cortex-A72/Cortex-A53" | **Quad-Core ARM Cortex-A53 only** (`cpu@0`..`cpu@3`, `arm,cortex-a53` @ 1.2 GHz). The Zynq UltraScale+ family has **no Cortex-A72** cores | CPU compute budget for software RAW compression is strictly 4x in-order Cortex-A53 cores @ 1.2 GHz |
| **Linux / PetaLinux Version** | PetaLinux 2022.2 (Linux 5.15) | **PetaLinux 2023.1 (`Linux 6.1.5-xilinx-v2023.1`, GCC 12.2.0, glibc 2.36, U-Boot 2023.01)** | Any custom kernel module or userspace library must target Linux 6.1.5 / `glibc 2.36` |
| **Container Framing** | Mentioned GZIP offset extraction | Fully decoded the 8-section `"wfsa"` (`asfw`) container, 24-byte section headers, 4-byte trailers, and Section 7 (`idx `) master directory | Enables deterministic parsing and verification of all 8 container sections |
| **Bootloader & Bitstream Encryption** | Did not distinguish encrypted vs. unencrypted ZynqMP partitions | Proved that `u-boot.elf`, `FLASH.UB`, `RAMDISK.UB`, `ROOTFS.BIN`, and expansion bitstreams (`FMOD*.BIN`) are **unencrypted**, whereas `phoenix_fsbl.elf`, `phoenix_boot.bin`, `APP0000.BIN` (Cortex-R5), and all 16 `DPGA00XX.BIN` ZynqMP FPGA bitstreams are **AES-GCM encrypted (`EFUSE_RED_KEY`)** | Linux userspace/kernel (`ROOTFS.BIN`, `FLASH.UB`) can be inspected and modified in research, whereas `DPGA00XX.BIN` and Cortex-R5 `APP0000.BIN` cannot be decrypted or modified without the eFUSE key |
| **Primary Recording Engine Location** | Assumed Linux `video_pipeline` handled main recording | Proved a split **AMP architecture**: **ProRes, ProRes RAW, and DNxHR/DNxHD** are encoded in **dedicated encrypted FPGA bitstreams (`DPGA00XX.BIN`)** controlled by the **Cortex-R5 (`APP0000.BIN`)**, while Linux `video_pipeline` handles **H.264/H.265 (VCU)**, streaming (`streaming_pl`), and YUV pass-through via `/dev/copro_comms_data` | Fundamental architectural discovery for Phase 3–5 custom codec integration |

---

## 6. Reproducibility Commands

All extraction steps were executed using deterministic Python scripts stored in `firmware/extracted/`:
```powershell
# 1. Verify original firmware hash
Get-FileHash firmware/original/ATOMNJV.FW -Algorithm SHA256

# 2. Extract container tables and FAT16 manifests
python firmware/extracted/extract_fdt_fit.py
python firmware/extracted/generate_inventories.py
```
