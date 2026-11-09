# VERDANOVE NINJA LAB

**Project:** Verdanove — Atomos Ninja V Custom RAW Recorder Research  
**Project Owner:** Anass Hlaibi  
**Target Hardware:** Original Atomos Ninja V (5-inch monitor-recorder, AtomOS 11.19.00 baseline)  
**Primary Camera Source:** Nikon ZR  
**Current Phase:** Phase 0 — Environment & Asset Verification (Completed)

---

## 1. Mission & Scope

Verdanove Ninja Lab is a structured embedded-systems, firmware reverse-engineering, FPGA, and video-codec research repository investigating whether the original **Atomos Ninja V** firmware and recording pipeline can be extended to support a compressed RAW recording workflow:

- Preserve **12-bit RAW** sensor data whenever the physical source interface provides genuine 12-bit RAW information.
- Investigate compressed **Nikon R3D NE** workflows and **Blue Compressor** (TICO-RAW / JPEG XS / high-efficiency Bayer compression) on AArch64 Linux.
- Evaluate real-time encoding feasibility on the Ninja V's Zynq UltraScale+ MPSoC platform.
- Retain standard Ninja V monitoring tools, SSD recording reliability, and post-production NLE compatibility (DaVinci Resolve / REDCINE-X PRO).

---

## 2. Critical Engineering Constraints

1. **Target Device Specificity:** All research targets the original **Atomos Ninja V** (`ATOMNJV.FW`, AtomOS `11.19.00`), *not* the Ninja V+, Ninja Ultra, Ninja RAW, or Ninja TX.
2. **Nikon ZR HDMI Signal Truth:** While the Nikon ZR records 12-bit R3D NE internally, its HDMI output during internal R3D NE recording mode is documented as **1080p 10-bit 4:2:2 YCbCr**. A 10-bit 4:2:2 HDMI signal cannot be converted into genuine 12-bit Bayer RAW by repackaging headers or encoders. Any 12-bit external recording workflow requires verifying whether the Nikon ZR exposes an uncompressed 12-bit RAW HDMI output mode (e.g., Nikon N-RAW / ProRes RAW HDMI output mode) or requires an alternative acquisition path.
3. **Hardware Realism:** No assumptions are made regarding Zynq UltraScale+ PL (FPGA) reconfigurability, Video Codec Unit (VCU) Bayer support, or Cortex-A53/A72 real-time throughput prior to empirical verification.

---

## 3. Safety & Integrity Rules

- **Immutable Firmware Baseline:** `firmware/original/ATOMNJV.FW` is stored read-only and verified via `SHA256SUMS`. It must never be modified or overwritten.
- **No Unverified Flashing:** Never flash modified containers to physical hardware during research phases without full boot/recovery verification and explicit sign-off.
- **Static Analysis First:** Never execute unknown firmware binaries on the host workstation.
- **Zero Credential Leakage:** Do not extract or publish proprietary cryptographic private keys or credentials into version control.

---

## 4. Repository Layout

See [`project_structure.md`](project_structure.md) for the complete directory tree and module descriptions.

| Directory | Purpose |
| :--- | :--- |
| `firmware/` | Immutable original `ATOMNJV.FW` image, extracted workspace, manifest, and SHA-256 hashes |
| `reverse-engineering/` | Container analysis, filesystem maps, U-Boot, Device Tree, ELF inventory, video pipeline & FPGA research |
| `hardware/` | SoC, PCB, HDMI interface, SATA/SSD, DRAM, and thermal/compute characterization |
| `compression/` | Blue Compressor analysis, TICO-RAW, R3D NE parsing, AArch64 cross-compilation, and CPU/GPU benchmarks |
| `recording-engine/` | Prototype capture, processing, encoding, SSD storage writer, metadata, and verification modules |
| `interface/` | Monitoring UI integration, compression controls, bit-depth truth indicators, and diagnostics |
| `tests/` | Firmware container integrity, codec bit-exactness, performance, NLE compatibility, and recovery tests |
| `documentation/` | Architecture specs, research findings, benchmarks, risk register, installation guides, and changelog |

---

## 5. Phase 0 Deliverables

- [`environment_report.md`](environment_report.md) — Workstation hardware, OS, WSL2, and toolchain audit.
- [`firmware_manifest.json`](firmware_manifest.json) — Metadata and cryptographic hashes for `ATOMNJV.FW` (`11.19.00`).
- [`SHA256SUMS`](SHA256SUMS) — Standard SHA-256 checksum file for `firmware/original/ATOMNJV.FW`.
- [`project_structure.md`](project_structure.md) — Full directory map and lifecycle rules.
- [`documentation/installation/tool_installation_guide.md`](documentation/installation/tool_installation_guide.md) — Installation & verification commands for missing host/WSL2 tools.
- [`documentation/installation/firmware_preservation_checklist.md`](documentation/installation/firmware_preservation_checklist.md) — Protocol for acquiring, verifying, and archiving official Ninja V firmware assets.
