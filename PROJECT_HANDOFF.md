# Verdanove Ninja V Project — Handoff / Current Status

**Last local review:** 2026-11-09  
**Purpose:** Summarize what is in this checkout, what has been attempted, and what is or is not verified. This file is a handoff, not a claim that the custom firmware works.

## Read this first

This repository began as a static research project for the original Atomos Ninja V and AtomOS 11.19.00. It now also contains prototypes for a sidecar recorder and custom firmware packages. The experiments have **not** been demonstrated to install, boot, or capture live camera frames on a physical Ninja V. Do not install a custom `.FW` file based on container checks, QEMU runs, or UI previews.

The original firmware is `firmware/original/ATOMNJV.FW` (319,558,064 bytes). It remains present and marked read-only. Its reported SHA-256 is `65e14e67bcc2624115300624d967634042601f23e9574e75ee7f06f2c8004be1`.

## Current local state

- Current branch: `phase-4-compression-engine`.
- Latest local commit observed: `b47dfb7`.
- Working tree has an edited `.github/workflows/ci.yml` and an untracked `tools/build_minimal_test_fw.py`.
- The `deploy/` folder contains several large experimental firmware images. They are build artifacts and are not proof of device compatibility.
- The original firmware and extracted filesystem payloads are excluded by `.gitignore`; they may exist locally without being in version control.

## Project history and work areas

### Phase 0–1: baseline and firmware analysis

Created repository layout, workstation report, firmware manifest and hashes. Extracted and inspected the ASFW container, FAT16 update image, QSPI boot images, FIT images, device trees, initramfs, root filesystem, and binary inventories. A correction record documents earlier report mistakes.

Key files:

- `README.md`, `project_structure.md`
- `environment_report.md`, `firmware_manifest.json`, `SHA256SUMS`
- `firmware_analysis_report.md`, `filesystem_inventory.md`, `filesystem_map.md`
- `architecture_report.md`, `service_inventory.md`, `fpga_inventory.md`
- `documentation/findings/phase1_corrections.md`
- `tools/phase1_evidence.py`, `reverse-engineering/evidence/phase1_evidence.json`
- `reverse-engineering/device-tree/`, `reverse-engineering/filesystem/`, `reverse-engineering/container-analysis/`, `reverse-engineering/binaries/`

**Evidence boundary:** extracted-file sizes, hashes, strings, container fields, and device-tree properties are static observations. Claims about actual runtime behavior, encrypted content interpretation, and end-to-end video flow require independent confirmation.

### Phase 2: hardware capability research

`hardware_capability_report.md` discusses memory regions, input/storage rates, and theoretical CPU budgets. Some sections use assumptions or estimates. No physical Ninja V benchmark is included; theoretical limits must not be presented as measured hardware performance.

### Phase 3–4: UI concept and compression benchmark

`simulator.html`, `simulator_bridge.py`, and preview PNGs show a local UI concept. They are not the Ninja V firmware UI, and the prototype does not prove the real UI can be extended.

`compression/arm64-port/bench_ninja_4k.rs`, `compression/arm64-port/arm64_port_report.md`, and `compression/cpu-benchmarks/benchmark_results.csv` contain Blue Compressor experiments run as AArch64 under QEMU. QEMU verifies that an ARM64 binary can run under emulation; its timing is not a physical Cortex-A53 measurement. Input scenes are synthetic. The report's physical CPU speed estimate is not hardware-tested.

### Phase 5–6: recorder and IPC prototype

`recording-engine/vraw_daemon.c`, `recording-engine/storage/*.c`, and `reverse-engineering/video-pipeline/service.proto` explore DNG writing and a hypothesized video IPC path. Supporting notes are in:

- `documentation/findings/phase5_video_pipeline_ipc_protocol.md`
- `documentation/findings/phase6_hardware_execution_vectors.md`
- `tests/test_ipc_client.py`, `tests/service_pb2.py`, `tests/verify_dng.py`
- `reverse-engineering/video-pipeline/fake_copro_interceptor.c`

The recorder has a synthetic-frame fallback. A successful synthetic/QEMU DNG write does not prove that the daemon receives real frames from the device. The proposed Unix socket / DMA-BUF handoff must be verified against the actual AtomOS runtime and protocol before describing this as live capture.

### Phase 7–9: SSD sidecar and custom firmware experiments

`deploy/ssd_payload/` contains an ARM64 daemon binary, config, shell launchers, and setup notes. The SSD autorun idea is not established as a stock Atomos feature; extracted automount rules do not demonstrate that the device runs scripts from inserted SSDs. Shell checks claiming RAM-only writes are not a substitute for verifying mount/overlay behavior on hardware.

`tools/build_spidi_package.py`, `tools/build_clean_spidi_package.py`, `tools/build_verified_spidi_fw.py`, and `tools/build_minimal_test_fw.py` manipulate/repack firmware sections and UI resources. `deploy/` contains these experimental `.FW` outputs:

- `ATOMNJV.FW`
- `ATOMNJV_SPIDI.FW`
- `ATOMNJV_CLEAN_SPIDI.FW`
- `ATOMNJV_SPIDI_VERIFIED.FW`
- `ATOMNJV_MINIMAL_TEST.FW`

The word “verified” in a filename means at most that software checks ran on the package structure/checksums. It does **not** mean Atomos accepts the image, the device boots it, the UI renders correctly, or recovery works. The custom firmware has not been verified on physical hardware. Do not flash it.

## Top-level directory map

| Path | Contents / purpose |
|---|---|
| `compression/` | Blue Compressor ARM64 benchmark source, report, and CSV results; cloned upstream repo may be ignored/untracked. |
| `deploy/` | Experimental firmware images, sidecar scripts, SSD payload, and setup documentation. |
| `documentation/` | Architecture, installation, deployment manifest, and phase findings/corrections. |
| `firmware/` | Firmware metadata/hashes, original baseline, and extracted analysis workspace. Original/extracted binaries are ignored by Git. |
| `hardware/` | Planned hardware research structure; mostly placeholders. |
| `interface/monitoring/` | Simulator preview/thumbnail images. |
| `recording-engine/` | Recorder C source, DNG writers, Makefile. |
| `reverse-engineering/` | Binary inventories, firmware container tables, device trees, evidence, filesystem and service/FPGA analyses. |
| `tests/` | IPC client, DNG tag checker, and sample test output; these are not a physical-device validation suite. |
| `tools/` | Evidence-generation, parsing, CRC, repacking, and experimental minimal firmware build scripts. |
| `simulator.html`, `simulator_bridge.py` | Local browser mockup and bridge, not firmware. |

For a complete path-by-path local inventory, run `rg --files` from the repository root. Large extracted filesystems and ignored upstream/build artifacts are intentionally excluded from this README's tracked-source summary.

## Main known gaps / risks

1. No verified, real camera frame stream into `vraw_daemon`.
2. No confirmed Atomos extension hook that runs the SSD sidecar automatically.
3. No physical-device test of a modified firmware package, boot, rollback, or recovery.
4. DNG verification checks selected TIFF/DNG tags; it does not establish complete CinemaDNG conformance or DaVinci Resolve compatibility.
5. QEMU speed and host SSD write speed do not establish Ninja V CPU or SATA performance.
6. A UI asset edit or generated preview does not establish the display uses that asset in the way assumed.
7. Earlier project reports had inaccuracies; use the correction record and primary extracted artifacts rather than treating every narrative claim as fact.

## Recommended next steps

1. Preserve the original firmware and keep all custom `.FW` files off the Ninja V.
2. Ask the agent for a handoff listing exact files changed, build commands/results, and which image asset was changed. Ask it to label each finding as inspected, emulated, or hardware-tested.
3. Reconfirm any modified package byte-for-byte against the untouched baseline and inspect the minimal build script before drawing conclusions.
4. Validate the DNG layout with an independent TIFF/DNG parser and real Resolve import using synthetic files only.
5. Investigate the IPC interface using the actual stock software/device before claiming live-frame access.
6. Only consider a real-device experiment after a recovery plan and a clearly bounded, reversible test are established.

## Basic local inventory commands

```powershell
rg --files
rg --files -g '!firmware/extracted/**' -g '!compression/blue-compressor/repo/**'
git status --short --branch
git log --oneline --decorate -20
```
