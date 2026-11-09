# Phase 1 Deliverable: Filesystem Inventory & Storage Map (`ATOMNJV.FW` — AtomOS 11.19.00)

- **Project:** Verdanove Ninja Lab
- **Target Device:** Original Atomos Ninja V (5-inch model)
- **Firmware Baseline:** AtomOS `11.19.00` (`ATOMNJV.FW`)

---

## 1. Multi-Layer Filesystem Hierarchy Overview

Static extraction of `ATOMNJV.FW` identified **three distinct filesystem layers** embedded inside the firmware package:

| Layer | Source Payload | Compression | Decompressed Size | Filesystem Type | Volume ID / UUID | Total Entries | Purpose |
|---|---|---|---:|---|---|---:|---|
| **Layer 1: Firmware Staging Volume** | `sec3_xbin_0x11111111.bin` (`294,387,712` B) | GZIP (`1f 8b 08`) + `0xFF` flash pad | `355,729,408` B (`339.25 MiB`) | **FAT16** (`mkfs.fat`) | Serial `0xd186df06` | `40` files | Stores Cortex-R5 firmware, UI resource pack, 16 ZynqMP FPGA bitstreams (`DPGA*.BIN`), expansion module bitstreams (`FMOD*`/`XMOD*`), MCU firmware (`GECKO_FW.BIN`, `DOCKUSB.BIN`), `FLASH.UB`, `RAMDISK.UB`, and `ROOTFS.BIN` |
| **Layer 2: Initramfs (`RAMDISK.UB`)** | `fat16_fs/RAMDISK.UB` -> `ramdisk-1` (`36,203,149` B) | U-Boot FIT -> GZIP | `122,461,184` B (`116.79 MiB`) | **SVR4 `newc` CPIO** | N/A | `1,677` entries | Initial RAM disk (`ramdisk.cpio`); runs `/init` to mount eMMC partitions or launch recovery mode |
| **Layer 3: Production Linux RootFS (`ROOTFS.BIN`)** | `fat16_fs/ROOTFS.BIN` (`114,557,385` B) | GZIP (`1f 8b 08`, name `atomos-image-minimal-atomos_ninjav.ext4`) | `381,229,056` B (`363.57 MiB`) | **Linux `ext4`** (1024-byte blocks) | `9b8f9d1a-bd53-4a10-8432-605efa2b7694` | `2,980+` inodes | Production PetaLinux 2023.1 (`glibc 2.36`, SysVinit) root filesystem mounted on `/dev/mmcblk0p2` |

---

## 2. Layer 1: FAT16 Firmware Staging Filesystem (`sec3_decompressed.img`)

- **Decompressed SHA-256:** `af228d9ecf1c6b40ee098e8c926e0be28da0ef23d652d6338c78e262c7042459`
- **Geometry:** `512` bytes/sector, `16` sectors/cluster (`8,192` bytes/cluster), `1` reserved sector, `2` FATs, `512` root directory entries, `694,784` total sectors (`355,729,408` bytes).

### Complete Inventory of All 40 Files in `fat16_fs/`

| # | Filename | Size (Bytes) | SHA-256 | Format / Magic | Role & Identification |
|---:|---|---:|---|---|---|
| 1 | `APP0000.BIN` | `21,796,864` | `07ff96d11be0a6e1791a91f7f562bc16d658f4bfba35d05a00a1bdccdd86e095` | ZynqMP `XLNX` Boot Image (`EFUSE_RED_KEY`) | Production Cortex-R5 (`R5-0`) real-time OS & UI/recording controller (`startrek_noresources.elf`, load `0x64cb7238`) |
| 2 | `DAPP0000.BIN` | `21,164,928` | `647338090967f6690544095c32bd07e4bf130bc72125bddeeb6fc07582a238a5` | ZynqMP `XLNX` Boot Image (`EFUSE_RED_KEY`) | Diagnostic / factory test Cortex-R5 image (`startrek_noresources.elf`, load `0x64b87388`) |
| 3 | `DOCKUSB.BIN` | `137,228` | `4c99e7726658644139de7575a265868bb65f5b0d62194225461b90f32ce6f588` | Cypress FX3 (`CY` magic `43 59`) | Cypress EZ-USB FX3 (`ARM926EJ-S`) USB 3.0 UVC Video/Audio firmware for AtomX CAST (`ATOMX CAST`) |
| 4 | `DPGA0000.BIN` | `7,797,692` | `aa90249529bf38f48c8a9f578b18269923d6969cfdf6509a899b7c46a7d387a6` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `prores_pb_app.bit` — ProRes Playback FPGA bitstream (`type_id = 0x00`) |
| 5 | `DPGA0001.BIN` | `7,797,692` | `6e2046159c80ff0cf87809cd1ab2aa67ce99642fc07ab432a99c627b9bd91167` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `dnx_pb_app.bit` — DNxHR/DNxHD Playback FPGA bitstream (`type_id = 0x01`) |
| 6 | `DPGA0002.BIN` | `7,797,692` | `5d54d47ba6d591ab11c8bfbd803025aa322481f97409f4c36a4a3f95bfab1b58` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `prores_cp_app.bit` — ProRes Capture/Encode FPGA bitstream (`type_id = 0x02`) |
| 7 | `DPGA0003.BIN` | `7,797,692` | `ab24455d187e6d6870ff8aa47fa912b2fb2b4fa1f935ca51de9769d8bd34873e` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `dnx_cp_app.bit` — DNxHR/DNxHD Capture/Encode FPGA bitstream (`type_id = 0x03`) |
| 8 | `DPGA0005.BIN` | `7,797,692` | `e734e264fb023a0400b72b2855fa4a9ba63efca6472aa8410fd60ff95452e129` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `prraw_cp_app.bit` — ProRes RAW Capture/Encode (HDMI) FPGA bitstream (`type_id = 0x05`) |
| 9 | `DPGA0006.BIN` | `7,797,692` | `e400b4d12f285e96dc8cf113de9a10bc79b6f0f023c6c5d410079a96ef1b3f11` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `prraw_pb_app.bit` — ProRes RAW Playback FPGA bitstream (`type_id = 0x06`) |
| 10 | `DPGA0009.BIN` | `7,797,692` | `976f57d937e892ff605532015a7cf4293f28e7df7e35b0094d936c330558fd1d` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `cp_h265.bit` — H.265/HEVC Capture Pass-Through to VCU (`type_id = 0x09`) |
| 11 | `DPGA0010.BIN` | `7,797,692` | `ab24455d187e6d6870ff8aa47fa912b2fb2b4fa1f935ca51de9769d8bd34873e` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `dnx_cp_app.bit` — Identical SHA-256 to `DPGA0003.BIN` (`type_id = 0x0A`) |
| 12 | `DPGA0012.BIN` | `7,797,692` | `75567b7f5a608dc70623f49bfdb64f6d99a1ba85a53433818ac1290202ef5311` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `cp_prores_raw_sdi.bit` — ProRes RAW SDI Capture FPGA bitstream (`type_id = 0x0C`) |
| 13 | `DPGA0013.BIN` | `7,797,692` | `3ef23724f500fb9f98b32b8da912ab2d82807a4cf457050c0153a5063e700597` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `pb_h265.bit` — H.265/HEVC Playback from VCU (`type_id = 0x0D`) |
| 14 | `DPGA0014.BIN` | `7,797,692` | `84ca593855fa7f929b4de0027932592c3e9a50ef6269b06d2e846a25150fa0c5` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `cp_prores_cast.bit` — ProRes + AtomX CAST multi-input switcher (`type_id = 0x0E`) |
| 15 | `DPGA0015.BIN` | `7,797,692` | `76ec1138eb798fc0cb856f97b044f59f9f635fa9749994a2da52fc3f1940b24d` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `cp_dnx_cast.bit` — DNx + AtomX CAST multi-input switcher (`type_id = 0x0F`) |
| 16 | `DPGA0017.BIN` | `7,797,692` | `4c99cc04bd3706980268a4406f4e4dc7d50666927cb41e7f7675971849d56137` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `cp_prores_stream.bit` — ProRes Capture + Live Stream (`type_id = 0x11`) |
| 17 | `DPGA0018.BIN` | `7,797,692` | `1c860f83037c66664f6d9e083ca5a7fd11c52f11a5195e9738735b3c4602ef8f` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `cp_dnx_stream.bit` — DNx Capture + Live Stream (`type_id = 0x12`) |
| 18 | `DPGA0019.BIN` | `7,797,692` | `0d05953c7cf48929b0363f9446e06846646bc7212eb3e7d19044d60336386958` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `cp_h265_stream.bit` — H.265 Capture + Live Stream (`type_id = 0x13`) |
| 19 | `DPGA0020.BIN` | `7,797,692` | `43f48685c3727ca290860565d9fb270a1b1b6d41c3c94878eb012c7147d09c44` | ZynqMP `XLNX` PL Bitstream (Encrypted) | `pb_h265_stream.bit` — H.265 Playback + Live Stream (`type_id = 0x14`) |
| 20 | `FLASH.UB` | `8,225,532` | `8db87100c954dc2dc33eb3cf0f3b1e55046bd90d8ab2b3a9bf3be9662d13895d` | Flattened Image Tree (`0xd00dfeed`) | Unencrypted U-Boot FIT containing Linux 6.1.5 kernel (`kernel-1`) + `fdt-system.dtb` |
| 21 | `FMODDOCK.BIN` | `2,192,115` | `c85399c3a7fd7b1332ab982610c3214b465722905dc715a66e22fc28ec69540b` | Xilinx `.bit` (Unencrypted) | Xilinx Artix-7 (`7a35tfgg484`) bitstream `ninjacast_top` for AtomX CAST |
| 22 | `FMODSTRM.BIN` | `1,753,735` | `43801a084c9615fc6655974bd8979d2fb3446c29d18414502bd9659761fc9567` | Xilinx `.bit` (Unencrypted) | Xilinx Artix-7 (`7a25tcsg325`) bitstream `ninjastream_top` for Atomos Connect |
| 23 | `GECKO_FW.BIN` | `15,607` | `47b698fb400eb6b1fd0d0f3e696d8fc36d4b37466ba606dc628e642661bf9fb7` | ARM Cortex-M Vector Table | Silicon Labs EFM32 Gecko system management & power microcontroller firmware |
| 24 | `MANIFEST.XMD` | `172` | `1ba0588296a0e4ef44816db2d8657f976ca71170332b003084cb2735ec0f340e` | ASCII CSV manifest | Maps expansion hardware IDs (`0..6`) to `XMOD*.BIN`, `FMOD*.BIN`, and `DOCKUSB.BIN` |
| 25 | `MD5SUMS` | `1,354` | `f8f8220ee8cc34ca851eb01ef4fa44ca5a0bf5a18bf096733bd4dc0400f36b17` | ASCII text | MD5 checksums of the 38 payload files in the FAT16 image |
| 26 | `RAMDISK.UB` | `36,204,196` | `fd890a9bf731d525d6b7fc97ec1053bd8097ffebae1ab88425c9145a3d74e956` | Flattened Image Tree (`0xd00dfeed`) | Unencrypted U-Boot FIT containing `ramdisk.cpio.gz` (`ramdisk-1`) |
| 27 | `RES0001.BIN` | `19,357,968` | `6f4b321694bc34337bf5027f8c563a0de4fa321459efab3315bd5949cf87f519` | ZynqMP `XLNX` Image (Unencrypted) | UI resource pack `startrek.resource_pack.p32` loaded into DDR at `0x44000000` for Cortex-R5 UI |
| 28 | `ROOTFS.BIN` | `114,557,385` | `8489cebf754ca1cf94489de6bdcc6f455cb48f3e3b8d9a39ca7b89c80d0e0470` | GZIP (`atomos-image-minimal-atomos_ninjav.ext4`) | Compressed production Linux `ext4` root filesystem (`381,229,056` B decompressed) |
| 29 | `SYNC0001.BIN` | `110,948` | `647ff2709be0ca438a85ce71bcdf59a7bd02916c086104673602080a943dbbd3` | AirGlu Sub-GHz RF MCU FW | `AirGlu2 Module Application v1.4.25` (Sub-GHz timecode sync transceiver firmware) |
| 30 | `SYNC0002.BIN` | `124,016` | `3f3bc4f1fb52b6333a8a53f6ca115f092d176ab63091f918d3540a960cb0ee86` | Nordic SoftDevice / BLE Stack | BLE peripheral stack for AtomX Sync / Atomos Connect |
| 31 | `SYNC0003.BIN` | `36,240` | `781ce13b155727b9cbdf6c7b4de4ee01d15d531be42a2be25ec26c15f0cc757e` | BLE Bootloader / App | `ATM2_BEL_APP` (`Timecode Systems Ltd`) |
| 32 | `SYNC0004.BIN` | `111,012` | `bf5f99220db5fd6bf6468eb41357ebbc516462ff1bc3f8ed9f6dc9125544711b` | AirGlu2 Sub-GHz RF MCU FW | `AirGlu2 Module Application v2.1.5` |
| 33 | `SYNC0005.BIN` | `37,044` | `ef3f2a8b1a9cf5f73ca0ab153d56fd0b33880ce66335a6c7b2009dc3be23f9f6` | BLE App | `ATM2_BEL_APP` (`Timecode Systems Ltd`, updated revision) |
| 34 | `VERSION.TXT` | `13` | `d1955b339de6a5b6a0267f1281911548e0392363e52a199449c74263f7cc2bf1` | ASCII text | Contains `99.99.99-7121` |
| 35 | `XMODDOCK.BIN` | `8,993,332` | `7979f6b47949b036c242d37b55ef840f5aa56129379ca45169130a86d789b793` | ASCII JTAG SVF (`!Xilinx`) | Serial Vector Format JTAG programming stream for Artix-7 (`IDCODE 0362d093`) on AtomX CAST |
| 36 | `XMODSDI.BIN` | `1,004,132` | `1389e9234fb823eb792919402555ff9044ff4d845c90852ffca975628d730350` | ASCII JTAG SVF (`!Quartus`) | Intel Quartus Prime 18.0 SVF for **Intel MAX 10 (`10M04SC`)** on AtomX SDI module |
| 37 | `XMODSDIN.BIN` | `7,797,692` | `aa90249529bf38f48c8a9f578b18269923d6969cfdf6509a899b7c46a7d387a6` | ZynqMP `XLNX` PL Bitstream | Identical SHA-256 to `DPGA0000.BIN` (`prores_pb_app.bit`) |
| 38 | `XMODSTRM.BIN` | `7,199,656` | `c852e81ef1f42c44d4160ba0f442a7fa48b2ef995efeb5074195605158c3ec5f` | ASCII JTAG SVF (`!Xilinx`) | Serial Vector Format JTAG programming stream for Artix-7 (`IDCODE 037c2093`) on Atomos Connect |
| 39 | `XMODSYN.BIN` | `1,004,132` | `94b211a8475a624b043fd7911ef91367cf977d7d02660211622a40615471bc71` | ASCII JTAG SVF (`!Quartus`) | Intel Quartus Prime 18.0 SVF for **Intel MAX 10 (`10M04SC`)** on AtomX Sync module |
| 40 | `XMODSYNN.BIN` | `7,797,692` | `aa90249529bf38f48c8a9f578b18269923d6969cfdf6509a899b7c46a7d387a6` | ZynqMP `XLNX` PL Bitstream | Identical SHA-256 to `DPGA0000.BIN` (`prores_pb_app.bit`) |

---

## 3. Layer 2: Initramfs (`RAMDISK.UB` -> `ramdisk.cpio`)

- **Decompressed Size:** `122,461,184` bytes (`1,677` files/directories/symlinks)
- **Key Boot Script (`/init`):**
  - Checks `/proc/cmdline` for `recovery`.
  - In normal mode, waits for `/dev/mmcblk0p2` (eMMC partition 2), runs `e2fsck -y /dev/mmcblk0p2`, mounts it at `/rootfs`, and executes `exec switch_root /rootfs /sbin/init`.
  - In recovery/firmware update mode, stays in initramfs and runs `/etc/init.d/rcS` to execute firmware flashing utilities (`flashcp`, `dd`, `fw_setenv`).

---

## 4. Layer 3: Production Linux `ext4` Root Filesystem (`ROOTFS.BIN`)

- **Decompressed Image:** `firmware/extracted/rootfs_decompressed.img` (`381,229,056` bytes)
- **Decompressed SHA-256:** `0fa79946a926e7cadf6a00012d2596b02c0cc6ed035aae1b77b3b531b0c94368`
- **OS Identification (`/etc/os-release`):**
  - `ID="petalinux"`
  - `NAME="PetaLinux"`
  - `VERSION="2023.1 (langdale)"`
  - `PRETTY_NAME="PetaLinux 2023.1 (langdale)"`
- **Target Mount Table (`/etc/fstab`):**
  - `/dev/root` -> `/` (`auto`, `defaults`)
  - `proc` -> `/proc`
  - `tmpfs` -> `/run`, `/var/volatile`
  - `/dev/mmcblk0p1` -> `/boot` (FAT16 boot & FPGA bitstream partition on internal 4 GB eMMC)
  - `/dev/mmcblk0p3` -> `/atomos` (`ext4` persistent configuration, calibration, activation keys, and logs partition on internal eMMC)

### 4.1 Directory Structure of `rootfs_ext4/`

| Directory | Contents & Key Files |
|---|---|
| `/bin` | BusyBox `1.35.0` applets, `bash`, `kmod`, `udevadm`, `dd`, `tar`, `gzip` |
| `/sbin` | `init.sysvinit`, `modprobe`, `insmod`, `e2fsck`, `mkfs.ext4`, `fdisk`, `ip`, `ifconfig`, `udhcpc` |
| `/etc` | `inittab`, `fstab`, `os-release`, `fw_env.config` (`/dev/mtd0 0x1E0000 0x20000 0x10000`), `init.d/` startup scripts (`atomos-init`, `load_fpga.sh`, `init_mem_layout.sh`) |
| `/lib` | `ld-linux-aarch64.so.1`, `libc.so.6` (`glibc 2.36`), `libstdc++.so.6.0.30`, and kernel modules under `/lib/modules/6.1.5-xilinx-v2023.1/` |
| `/usr/bin` | Primary Atomos daemons (`video_pipeline`, `streaming_pl`, `core_control`, `cloud_service`, `media_control`, `camera_control`, `audio_encoder`, `talkback_pl`, `ctrl_vcu`, `load_fpga`, `copro_debug`, `start_r5.sh`) |
| `/usr/lib` | GStreamer 1.20.5 (`libgstreamer-1.0.so.0.2005.0`), `gstreamer-1.0/` plugins (`libgstomx.so`, `libgstvideo4linux2.so`, `libgstrtmp2.so`, `libgstsrt.so`, `libgstndi.so`), Allegro DVT VCU libraries (`liballegro_encode.so`, `liballegro_decode.so`, `libOMX.allegro.core.so`), `libndi.so.5.5.3`, `librtmp.so.1`, `libsrt.so.1.4.2`, `libx264.so.163`, `libfdk-aac.so.2` |
| `/home/root` | Default root home directory |

