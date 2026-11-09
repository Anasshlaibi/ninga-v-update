# Phase 1 Deliverables Correction Record (Revision 2)

**Date:** 2026-11-09  
**Branch:** `phase-1-firmware-analysis`  
**Trigger:** Comprehensive audit against `tools/phase1_evidence.py` and extracted artifacts.

---

## 1. Summary of Corrected Discrepancies

| Artifact / Topic | Revision 1 (Erroneous Claim) | Revision 2 (Verified Ground Truth) |
|---|---|---|
| `video_pipeline` size | `597,688` bytes | **`2,879,712` bytes** (`b2a99dd9d834dc82...`) |
| `APP0000.BIN` size | `21,796,864` bytes | **`4,058,580` bytes** (`13ac9053cebe00db...`) |
| `DPGA*.BIN` sizes | `7,797,692` bytes each | **`8,096,828` bytes** each (15 files total) |
| Non-existent files in FAT16 | Listed `DPGA0010.BIN`, `MD5SUMS`, `VERSION.TXT` | **Do not exist**. Real files present: `DATA0000.BIN` (64 B), `FWFAILED.BIN` (2 MB), `PLS_WAIT.BIN` (238 KB), `ROOTFS.TXT` (42 B), `UBOOT.ENV` (256 KB) |
| Rootfs mount table (`/etc/fstab`) | Claimed `/dev/mmcblk0p1` -> `/boot`, `/dev/mmcblk0p3` -> `/atomos` | Real fstab mounts `/media/boot` (p1), `/media/resources` (p2), `/media/static` (p3), `/media/app` (p6), `/var/nonvolatile` (p7) |
| `sec5` QSPI contents | Claimed Linux `Image.gz`, `system.dtb`, `rootfs.cpio` | Contains `emergency.bit` (PL), `startrek_noresources.elf` (R5 @ 0x64b87388), `startrek.resource_pack.p32` (DDR @ 0x44000000). No Linux kernel. |
| `/etc/os-release` | Claimed present with PetaLinux 2023.1 | **Missing** from rootfs. Verified OS banner via `/etc/issue` (`PetaLinux 2023.1+release-S05010539`) and kernel banner. |
| Intel MAX 10 `10M04SC` | Implied mainboard component | Found inside `XMODSDI.BIN` and `XMODSYN.BIN` JTAG SVF headers: expansion module CPLD. |

All deliverables (`firmware_analysis_report.md`, `filesystem_inventory.md`, `service_inventory.md`, `fpga_inventory.md`, `architecture_report.md`) are now updated to Revision 2 ground truth.
