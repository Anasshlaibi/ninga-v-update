# Phase 2 — Hardware Architecture & Capability Verification Report

- **Project:** Verdanove Ninja Lab
- **Target Device:** Atomos Ninja V (Original 5-inch model)
- **SoC Identified:** **AMD/Xilinx Zynq UltraScale+ MPSoC `XCZU5EV`** (`atomos_ninjav_xczu5ev-xilinx-linux`)
- **Package / Speed Grade:** Form-factor portable video monitor/recorder (~10–15 W active system thermal budget)
- **Status:** Phase 2 Verification Completed

---

## 1. Verified Hardware Baseline & Subsystem Architecture

Empirical analysis of the device tree ([system.dts](file:///c:/Users/HELIOS%20NEO%2016/Documents/framatomos/verdanove-ninja-lab/reverse-engineering/device-tree/system.dts)), kernel configuration, and driver modules confirms the physical hardware architecture:

```
+---------------------------------------------------------------------------------------------------+
|                            Xilinx Zynq UltraScale+ MPSoC (XCZU5EV)                                 |
+------------------------------------+----------------------------------+---------------------------+
| APU: Application Processing Unit   | RPU: Real-Time Processing Unit   | PL: Programmable Logic    |
| - 4x ARM Cortex-A53 @ 1.2 GHz max  | - 2x ARM Cortex-R5F (Lockstep/   | - 256K Logic Cells        |
| - NEON SIMD engine per core        |   Split, runs startrek UI)       | - 1,248 DSP48E2 slices    |
| - 32 KB L1 I/D cache, 1 MB L2      | - Ultra-low latency I/O control  | - 16x DPGA*.BIN bitstreams|
| - Runs Linux 6.1.5 (PetaLinux)     | - Direct SATA / FPGA master      | - Hardware ProRes/DNx/RAW |
+------------------------------------+----------------------------------+---------------------------+
| VCU: Video Codec Unit (Hard IP)    | PMU: Platform Management Unit    | GPU: ARM Mali-400 MP2     |
| - Allegro DVT IP Core              | - Dedicated MicroBlaze core      | - 2D/3D UI acceleration   |
| - 4K60 10-bit 4:2:2 H.264 / H.265  | - Power, reset, thermal control  | - Not suitable for compute|
| - NO RAW / Bayer / TICO support    | - CSU secure boot & AES decrypt  |   (GLES 2.0, no OpenCL)   |
+------------------------------------+----------------------------------+---------------------------+
| System Memory: 2 GiB DDR4 (32-bit/64-bit bus)                                                     |
| - 416 MiB: Linux kernel & userspace                                                               |
| - 272 MiB: codec_input (0x1b000000 - uncompressed video frame buffers)                            |
| - 832 MiB: codec_output (0x2c000000 - dynamic CMA pool for VCU / CoPro)                           |
| - 512 MiB: Cortex-R5 dedicated memory (0x60000000 - 0x7fffffff)                                  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Theoretical vs. Real-World Throughput Limits

### 2.1 Storage Interface (SATA 3.0 AHCI)
- **Controller:** Integrated ZynqMP AHCI SATA 3.0 controller (`ceva,ahci-1v84` at `0xfd0c0000`), physically routed to the Master Caddy II / AtomX SSDmini slot.
- **Physical Link Speed:** SATA Revision 3.0 (6.0 Gbps / 600 MB/s theoretical line rate).
- **Practical Storage Limit:** **~520 to 550 MB/s** sequential write (limited by SATA 8b/10b encoding, AHCI protocol overhead, and standard 2.5-inch SATA SSD controllers like AtomX SSDmini / Angelbird / Samsung 870 EVO).

### 2.2 HDMI 2.0 Input Path
- **HDMI RX Physical Interface:** HDMI 2.0b routed into the ZynqMP Programmable Logic (PL) GTH/GTY transceivers.
- **Maximum Input Resolution:** Up to 4K DCI (4096×2160) at 60 fps (up to 18 Gbps TMDS).
- **RAW Input Signals (e.g. Nikon ZR):** Uncompressed 12-bit Bayer raw frames transmitted across HDMI data channels using proprietary packetization.

---

## 3. Data Rate Math: 12-Bit Bayer RAW vs. Storage & Bandwidth

For a 12-bit Bayer sensor pattern (1 sample per pixel, 1.5 bytes packed per pixel):

| Video Format & Resolution | Pixel Count / Frame | Frame Size (12-bit packed) | Frame Time | Uncompressed Data Rate (MB/s) | Uncompressed Bitrate (Gbps) | Fits Uncompressed on SATA 3 SSD? (550 MB/s max) | Minimum Compression Ratio Required for SATA |
|---|---|---:|---:|---:|---:|---|---|
| **4K DCI (4096×2160) 60 fps** | 8,847,360 | 12.66 MB | 16.67 ms | **759.4 MB/s** | 6.37 Gbps | **NO (Exceeds SATA by 38%)** | **≥ 1.38 : 1** |
| **4K UHD (3840×2160) 60 fps** | 8,294,400 | 11.87 MB | 16.67 ms | **711.9 MB/s** | 5.97 Gbps | **NO (Exceeds SATA by 29%)** | **≥ 1.29 : 1** |
| **4K UHD (3840×2160) 30 fps** | 8,294,400 | 11.87 MB | 33.33 ms | **356.0 MB/s** | 2.99 Gbps | **YES** | 1.00 : 1 (Uncompressed fits) |
| **4K UHD (3840×2160) 24 fps** | 8,294,400 | 11.87 MB | 41.67 ms | **284.8 MB/s** | 2.39 Gbps | **YES** | 1.00 : 1 (Uncompressed fits) |
| **FHD (1920×1080) 60 fps** | 2,073,600 | 2.97 MB | 16.67 ms | **178.0 MB/s** | 1.49 Gbps | **YES** | 1.00 : 1 (Uncompressed fits) |
| **FHD (1920×1080) 24 fps** | 2,073,600 | 2.97 MB | 41.67 ms | **71.2 MB/s** | 0.60 Gbps | **YES** | 1.00 : 1 (Uncompressed fits) |

> **Key Storage Finding:** At 4K 24 fps and 30 fps, uncompressed 12-bit RAW data rates (**285–356 MB/s**) easily fit within standard SATA 3.0 SSD write speeds (**~520 MB/s**). Only 4K 50/60 fps strictly requires real-time compression to avoid dropping frames over SATA.

---

## 4. Compute Feasibility: Quad-Core Cortex-A53 @ 1.2 GHz

If compression (such as Blue Compressor / TICO-RAW / JPEG XS) were to run **in software on the Linux APU**, what is the mathematical cycle budget available per pixel?

- **Total Combined APU Compute Clock:** 4 cores × 1.2 GHz = **4.80 Giga-cycles/second** (assuming 100% CPU saturation on all 4 cores dedicated solely to compression, 0% left for OS/networking).

### Cycle Budget per Pixel

| Format | Frame Rate | Pixels / Second | Max Cycle Budget (100% 4-core utilization) | Practical Cycle Budget (70% load threshold) | Feasibility for Software Wavelet/Entropy Compression |
|---|---|---|---|---|---|
| **4K 60 fps** | 60 fps | 497.6 Million | **9.6 cycles / pixel** | **6.7 cycles / pixel** | **IMPOSSIBLE on CPU** (wavelet transform alone requires >25 cycles/pixel) |
| **4K 30 fps** | 30 fps | 248.8 Million | **19.3 cycles / pixel** | **13.5 cycles / pixel** | **CRITICAL / UNLIKELY** (even heavily vectorized NEON code exceeds 20 cycles) |
| **4K 24 fps** | 24 fps | 199.1 Million | **24.1 cycles / pixel** | **16.9 cycles / pixel** | **BORDERLINE** (requires extreme assembly optimization, zero cache misses) |
| **FHD 60 fps**| 60 fps | 124.4 Million | **38.6 cycles / pixel** | **27.0 cycles / pixel** | **FEASIBLE** with SIMD NEON parallelism |
| **FHD 24 fps**| 24 fps | 49.8 Million | **96.5 cycles / pixel** | **67.5 cycles / pixel** | **FEASIBLE** in software |

### Why Real-Time 4K60 Software Compression Cannot Run on Cortex-A53
1. **Instruction Budget:** A standard discrete wavelet transform (DWT 5/3 or 9/7 used in JPEG 2000 / TICO-RAW) combined with quantization, bitplane coding, and Golomb-Rice / arithmetic entropy encoding typically requires **40 to 120 CPU instructions per pixel**. At 9.6 cycles per pixel, an in-order Cortex-A53 core cannot execute this even with 100% dual-issue efficiency.
2. **Memory Contention:** Fetching 712 MB/s of input frames, writing 200–350 MB/s of compressed bitstream, while the display controller reads the 1080p monitoring framebuffer across a shared 32-bit/64-bit DDR4 bus will incur severe cache thrashing on a 1 MB shared L2 cache.
3. **Conclusion:** **Real-time 4K software RAW compression on the Ninja V's Cortex-A53 CPU is computationally impossible.** The Ninja V only achieves 4K ProRes and ProRes RAW recording because **ProRes / ProRes RAW encoding is executed entirely inside the hardware FPGA fabric (`DPGA0002.BIN` / `DPGA0005.BIN`)**, NOT on the CPU.

---

## 5. Architectural Paths Forward for the Project

Given that the FPGA bitstreams are hardware-encrypted and the Cortex-A53 CPU cannot compress 4K RAW in real time:

| Architecture | Description | Pros | Cons / Blockers |
|---|---|---|---|
| **Path A: Direct Uncompressed 12-bit RAW Recording (4K 24/30p)** | Bypass compression entirely; pipe uncompressed 12-bit packed Bayer frames from HDMI RX into DDR and write directly to SATA SSD (~285–356 MB/s). | • Zero CPU compression load<br>• True lossless 12-bit sensor data<br>• Fully compatible with DaVinci Resolve (CinemaDNG / DNG sequence) | • Requires finding if HDMI RX exposes uncompressed Bayer into DDR<br>• Higher storage usage (1 TB ≈ 45–60 mins) |
| **Path B: Atomos Native ProRes RAW Workflow** | Use existing verified `DPGA0005.BIN` (`prraw_cp_app.bit`) and transcode to R3D / Nikon RAW offline on the workstation. | • 100% reliable 4K60 hardware recording<br>• Preserves 12-bit Bayer RAW | • Does not record native R3D in-camera |
| **Path C: Companion Expansion Module (FPGA / NPU Sidecar)** | Use the AtomX expansion port (PCIe / high-speed transceivers) with an external FPGA/processor (e.g. Artix Ultrascale+ or Jetson) to run Blue Compressor. | • Offloads compute from Ninja V<br>• Keeps monitoring UI intact | • Requires custom expansion hardware |

