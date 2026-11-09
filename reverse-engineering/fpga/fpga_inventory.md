# Phase 1 — FPGA & Programmable Logic Inventory (AtomOS 11.19.00)

> [!IMPORTANT]
> **Revision 2 — evidence-based rewrite.** Every entry below was verified against extracted files. See [phase1_corrections.md](documentation/findings/phase1_corrections.md).

## 1. Summary
There are three groups of programmable-logic files in the firmware:
1. **ZynqMP on-chip PL bitstreams (15 files in FAT16, 1 in section 5):** all 8,096,828 bytes each, wrapped as Xilinx boot images (`XLNX`), high entropy (~7.999), no clear-text bitstream headers.
2. **Accessory Artix-7 bitstreams (2 files in FAT16):** unencrypted raw `.bit` files for expansion modules, with visible Vivado headers.
3. **Accessory Intel MAX 10 programming files (2 files in FAT16):** ASCII SVF files for CPLDs on expansion modules.

## 2. ZynqMP On-Chip PL Files (`DPGA*.BIN`) — VERIFIED

Every `DPGA*.BIN` file in `fat16_fs/` has:
- Size: exactly 8,096,828 bytes.
- Key-source word in header: `0xa5c3c5a3`.
- Internal image name (extracted from the XLNX image header table by `tools/phase1_evidence.py`):

| File | Size (bytes) | Internal Image Name | SHA-256 (first 16) | Inferred Function |
|---|---:|---|---|---|
| `DPGA0000.BIN` | 8,096,828 | `prores_pb_app.bit` | `0047f4cc86df7665…` | ProRes playback |
| `DPGA0001.BIN` | 8,096,828 | `dnx_pb_app.bit` | `77e1deb131164636…` | DNx playback |
| `DPGA0002.BIN` | 8,096,828 | `prores_cp_app.bit` | `082be856a564d021…` | ProRes capture |
| `DPGA0003.BIN` | 8,096,828 | `dnx_cp_app.bit` | `66aa0bd2b3f96b96…` | DNx capture |
| `DPGA0005.BIN` | 8,096,828 | `prraw_cp_app.bit` | `80f061b0e15f5065…` | ProRes RAW capture |
| `DPGA0006.BIN` | 8,096,828 | `prraw_pb_app.bit` | `2f0a14682ed02a20…` | ProRes RAW playback |
| `DPGA0009.BIN` | 8,096,828 | `cp_h265.bit` | `e2be78184d90745d…` | H.265 capture (feeds VCU) |
| `DPGA0012.BIN` | 8,096,828 | `cp_prores_raw_sdi.bit` | `009ae29fc9fe0a35…` | ProRes RAW over SDI |
| `DPGA0013.BIN` | 8,096,828 | `pb_h265.bit` | `1283e0f9f961326d…` | H.265 playback |
| `DPGA0014.BIN` | 8,096,828 | `cp_prores_cast.bit` | `d836a6b859e87a5d…` | ProRes + AtomX CAST |
| `DPGA0015.BIN` | 8,096,828 | `cp_dnx_cast.bit` | `b5b515938d4b1273…` | DNx + AtomX CAST |
| `DPGA0017.BIN` | 8,096,828 | `cp_prores_stream.bit` | `3417ff6b3d809c90…` | ProRes + streaming |
| `DPGA0018.BIN` | 8,096,828 | `cp_dnx_stream.bit` | `4fe48b8f009d6395…` | DNx + streaming |
| `DPGA0019.BIN` | 8,096,828 | `cp_h265_stream.bit` | `7e623aaaf4a108cd…` | H.265 + streaming |
| `DPGA0020.BIN` | 8,096,828 | `pb_h265_stream.bit` | `9662ac9ba8d63413…` | H.265 playback + streaming |

In addition, Section 5 partition 4 contains `emergency.bit` (7,797,692 bytes, payload entropy 7.999).

**Correction from Revision 1:**
- Files `DPGA0004`, `DPGA0007`, `DPGA0008`, `DPGA0010`, `DPGA0011`, `DPGA0016` **do not exist** in this firmware release.
- Revision 1 listed `DPGA0010.BIN` as identical to `DPGA0003.BIN`. In fact, `DPGA0010.BIN` is not in the FAT image at all.
- Every existing `DPGA*.BIN` file has a unique SHA-256 hash.

## 3. Accessory Artix-7 Bitstreams — VERIFIED

These files are standard, unencrypted Xilinx bitstreams with readable ASCII headers:

| File | Size (bytes) | Target Device | Design Name | Tool & Build Date |
|---|---:|---|---|---|
| `FMODDOCK.BIN` | 2,192,121 | `7a35tfgg484` (Artix-7 35T) | `ninjacast_top` | Vivado 2021.1, 2023/05/15 23:38:08 |
| `FMODSTRM.BIN` | 553,189 | `7a25tcsg325` (Artix-7 25T) | `ninjastream_top` (compressed) | Vivado 2021.1, 2022/11/14 00:41:15 |

Associated SVF files (used to program them over JTAG):
- `XMODDOCK.BIN` (4,402,292 bytes): SVF header references `expand_ninjacast_6462c16e.svf`.
- `XMODSTRM.BIN` (1,111,491 bytes): SVF header references `expand_ninjastream_63718e31.svf`.

## 4. Accessory Intel MAX 10 SVF Files — VERIFIED

- `XMODSDI.BIN` (3,671,179 bytes) and `XMODSYN.BIN` (3,671,129 bytes).
- Both contain comments from Intel Quartus Prime (build April 2018):
  `!Device #1: 10M04SC - /home/luke/projects/phoenix_scratch/fpga/syn/expansion/exp_common/output_files/exp_common.pof Sat Apr 25 10:32:03 2020`.
- **Finding:** The Intel MAX 10 `10M04SC` referenced in community reports is an **expansion-module CPLD** (AtomX SDI / AtomX Sync), programmed through the expansion connector. It is **not** proven to be on the Ninja V mainboard.

## 5. Security & Project Constraints

- The internal image names (`prores_cp_app.bit`, `prraw_cp_app.bit`, etc.) confirm that **codec implementations live in the PL bitstreams**.
- Because these bitstreams show high entropy and encrypted header flags, **we cannot disassemble, modify or rebuild them**.
- Therefore, the project **cannot inject a custom codec into the existing FPGA recording pipeline**. Any custom compression work must run on the A53 Linux CPU, the VCU (if compatible, which TICO-RAW is not), or on external hardware.
