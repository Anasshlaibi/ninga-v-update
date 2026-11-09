# Phase 1 — Filesystem Inventory (AtomOS 11.19.00)

> [!IMPORTANT]
> **Revision 2 — evidence-based rewrite.** Every number below comes from `reverse-engineering/filesystem/fat16_manifest.json` and `reverse-engineering/evidence/phase1_evidence.json`. See [phase1_corrections.md](documentation/findings/phase1_corrections.md).

## 1. Layers Overview
- **Layer 1:** FAT16 image inside section 3 (`sec3_decompressed.img`, 355,729,408 bytes, 40 files). Staging area for updates.
- **Layer 2:** Initramfs (`RAMDISK.UB` → `ramdisk.cpio`, 122,461,184 bytes, 1,677 entries).
- **Layer 3:** Root filesystem (`ROOTFS.BIN` → ext4 image, 381,229,056 bytes).

## 2. FAT16 File List (40 files) — VERIFIED

| # | Name | Size (bytes) | SHA-256 (first 16 hex) | Entropy | Classification |
|---:|---|---:|---|---:|---|
| 1 | `APP0000.BIN` | 4,058,580 | `13ac9053cebe00db…` | 7.999 | XLNX boot image, image name `startrek_noresources.elf` |
| 2 | `DAPP0000.BIN` | 4,058,580 | `c3fd74af1f0cf404…` | 7.999 | XLNX boot image, image name `startrek_noresources.elf` |
| 3 | `DATA0000.BIN` | 64 | `b0e087f4c09c8d18…` | 5.568 | 64-byte payload, last 4 bytes zero |
| 4 | `DOCKUSB.BIN` | 137,228 | `9b8511a3cd2a9c4b…` | 6.455 | magic `CY`, Cypress FX3 firmware |
| 5 | `DPGA0000.BIN` | 8,096,828 | `0047f4cc86df7665…` | 7.999 | XLNX boot image, `prores_pb_app.bit` |
| 6 | `DPGA0001.BIN` | 8,096,828 | `77e1deb131164636…` | 7.999 | XLNX boot image, `dnx_pb_app.bit` |
| 7 | `DPGA0002.BIN` | 8,096,828 | `082be856a564d021…` | 7.999 | XLNX boot image, `prores_cp_app.bit` |
| 8 | `DPGA0003.BIN` | 8,096,828 | `66aa0bd2b3f96b96…` | 7.999 | XLNX boot image, `dnx_cp_app.bit` |
| 9 | `DPGA0005.BIN` | 8,096,828 | `80f061b0e15f5065…` | 7.999 | XLNX boot image, `prraw_cp_app.bit` |
| 10 | `DPGA0006.BIN` | 8,096,828 | `2f0a14682ed02a20…` | 7.999 | XLNX boot image, `prraw_pb_app.bit` |
| 11 | `DPGA0009.BIN` | 8,096,828 | `e2be78184d90745d…` | 7.999 | XLNX boot image, `cp_h265.bit` |
| 12 | `DPGA0012.BIN` | 8,096,828 | `009ae29fc9fe0a35…` | 7.999 | XLNX boot image, `cp_prores_raw_sdi.bit` |
| 13 | `DPGA0013.BIN` | 8,096,828 | `1283e0f9f961326d…` | 7.999 | XLNX boot image, `pb_h265.bit` |
| 14 | `DPGA0014.BIN` | 8,096,828 | `d836a6b859e87a5d…` | 7.999 | XLNX boot image, `cp_prores_cast.bit` |
| 15 | `DPGA0015.BIN` | 8,096,828 | `b5b515938d4b1273…` | 7.999 | XLNX boot image, `cp_dnx_cast.bit` |
| 16 | `DPGA0017.BIN` | 8,096,828 | `3417ff6b3d809c90…` | 7.999 | XLNX boot image, `cp_prores_stream.bit` |
| 17 | `DPGA0018.BIN` | 8,096,828 | `4fe48b8f009d6395…` | 7.999 | XLNX boot image, `cp_dnx_stream.bit` |
| 18 | `DPGA0019.BIN` | 8,096,828 | `7e623aaaf4a108cd…` | 7.999 | XLNX boot image, `cp_h265_stream.bit` |
| 19 | `DPGA0020.BIN` | 8,096,828 | `9662ac9ba8d63413…` | 7.999 | XLNX boot image, `pb_h265_stream.bit` |
| 20 | `FLASH.UB` | 8,621,680 | `637824dd2b37b21b…` | 7.969 | U-Boot FIT: Linux kernel 6.1.5 + system.dtb |
| 21 | `FMODDOCK.BIN` | 2,192,121 | `52fddcdecffbce92…` | 1.222 | Xilinx Artix-7 bitstream: `ninjacast_top`, `7a35tfgg484` |
| 22 | `FMODSTRM.BIN` | 553,189 | `e5b5df5dd5bd0fd2…` | 1.303 | Xilinx Artix-7 bitstream: `ninjastream_top`, `7a25tcsg325` |
| 23 | `FWFAILED.BIN` | 2,088,960 | `0a56d97007e4874d…` | 1.332 | splash image (raw framebuffer data) |
| 24 | `GECKO_FW.BIN` | 15,607 | `57a8a21530deb918…` | 4.887 | microcontroller binary (Gecko) |
| 25 | `MANIFEST.XMD` | 122 | `57ccf532027dbb8f…` | 4.542 | ASCII table mapping module IDs to bitstreams |
| 26 | `PLS_WAIT.BIN` | 238,560 | `ce8f92a11b4fc19a…` | 0.999 | splash image (raw framebuffer data) |
| 27 | `RAMDISK.UB` | 53,341,780 | `b511780473656cd7…` | 7.981 | U-Boot FIT: kernel + DTB + ramdisk-1 |
| 28 | `RES0001.BIN` | 11,459,647 | `e3847c365581d30e…` | 7.828 | UI resource pack |
| 29 | `ROOTFS.BIN` | 99,365,392 | `95432401d029fb30…` | 7.976 | gzip → ext4 root filesystem (381,229,056 B) |
| 30 | `ROOTFS.TXT` | 42 | `775c02a3d9245bfb…` | 4.298 | `UUID=9b8f9d1a-bd53-4a10-8432-605efa2b7694` |
| 31 | `SYNC0001.BIN` | 67,686 | `2581819ce6e98245…` | 5.378 | Sync module radio firmware (`*AiGu1`) |
| 32 | `SYNC0002.BIN` | 24,698 | `2c3ad943d1168567…` | 5.228 | Sync module radio firmware (`*TFPAg`) |
| 33 | `SYNC0003.BIN` | 181,474 | `569a5b778c26c4a1…` | 5.266 | Sync module radio firmware (`*BLEag`) |
| 34 | `SYNC0004.BIN` | 246,781 | `fca4aa083e368977…` | 5.513 | Sync module radio firmware (`*AGu2c`) |
| 35 | `SYNC0005.BIN` | 127,633 | `c04a22be53a627af…` | 5.350 | Sync module radio firmware (`*AGu2s`) |
| 36 | `UBOOT.ENV` | 262,144 | `8a39d2abd3999ab7…` | 0.000 | 256 KiB all zero |
| 37 | `XMODDOCK.BIN` | 4,402,292 | `97056302d6601914…` | 4.195 | ASCII SVF: `expand_ninjacast_6462c16e.svf` |
| 38 | `XMODSDI.BIN` | 3,671,179 | `5ec2ca4d355bb683…` | 4.293 | ASCII SVF (Intel Quartus 2018): 10M04SC |
| 39 | `XMODSTRM.BIN` | 1,111,491 | `7eb8be28a36a7e68…` | 4.093 | ASCII SVF: `expand_ninjastream_63718e31.svf` |
| 40 | `XMODSYN.BIN` | 3,671,129 | `128b194731721efe…` | 4.293 | ASCII SVF (Intel Quartus 2018): 10M04SC |

Full SHA-256 sums are in `reverse-engineering/filesystem/fat16_manifest.json`.

## 3. Real Mount Table (`/etc/fstab` inside `ROOTFS.BIN`) — VERIFIED

```text
/dev/root       /                  auto  ro                                  1  0
proc            /proc              proc  defaults                            0  0
devpts          /dev/pts           devpts mode=0620,gid=5                    0  0
tmpfs           /run               tmpfs mode=0755,nodev,nosuid,strictatime  0  0
tmpfs           /var/volatile      tmpfs defaults                            0  0

/dev/mmcblk0p1  /media/boot        auto  defaults,ro,noatime                 0  2
/dev/mmcblk0p2  /media/resources   auto  defaults,ro,noatime                 0  2
/dev/mmcblk0p3  /media/static      auto  defaults,ro,noatime                 0  2
/dev/mmcblk0p6  /media/app         ext4  defaults,ro,noauto,noatime          0  2
/dev/mmcblk0p7  /var/nonvolatile   ext4  defaults,noauto,noatime,nofail,data=journal 0 2
```

Note: this corrects the earlier description, which claimed different mount points.

## 4. Manifest: `MANIFEST.XMD` — VERIFIED
Text contents:
```text
0 XMODSYN.bin 0193dd91 
1 XMODSDI.bin 0193cabf 
5 XMODDOCK.bin 6462c16e FMODDOCK.bin
6 XMODSTRM.bin 63718e31 FMODSTRM.bin
```
Maps accessory module IDs to programming streams.
