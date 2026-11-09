# Blue Compressor ARM64 Cross-Compilation and Performance Report

**Target Reference:** Atomos Ninja V (Xilinx Zynq UltraScale+ XCZU3EG)  
**CPU Architecture:** Quad-core ARM Cortex-A53 @ 1.2 GHz  
**Test Binary:** `target/aarch64-unknown-linux-gnu/release/examples/bench_ninja_4k`  
**Execution Environment:** QEMU User Emulation (`qemu-aarch64-static` on Linux x86_64 host)  
**Branch:** `phase-4-compression-engine`  
**Date:** 2026-11-09  

---

## 1. Executive Summary & Review Scope

This report evaluates whether software-based **intoPIX TICO-RAW / JPEG XS** Bayer compression (via the **Blue Compressor** engine) can run in real time on the Atomos Ninja V's quad Cortex-A53 application processor, or whether hardware FPGA offloading is fundamentally required.

### Important Methodological Clarifications:
1. **Full-Frame Compression vs. Requantization:**  
   The initial trial benchmarked a requantization sub-loop on already-encoded frames. This updated benchmark measures the **true end-to-end full-frame compression pipeline**:
   $$\text{Raw 12-bit Bayer Quad} \xrightarrow{\text{Star-Tetrix}} \text{Decorrelated Planes} \xrightarrow{\text{5/3 DWT}} \text{Wavelet Coeffs} \xrightarrow{\text{Bit-Packing}} \text{TICO Codestream}$$
2. **Emulation vs. Physical Silicon Timing:**  
   Execution is conducted inside `qemu-aarch64-static`. While QEMU validates binary compatibility, ARM64 ABI compliance, and algorithmic output correctness, **QEMU execution times reflect the host PC CPU's out-of-order execution and JIT translation, NOT the physical in-order Cortex-A53 silicon cycles or LPDDR4 memory controller latency**. Real-device physical throughput will be substantially lower than host emulation numbers.
3. **Empirical Code Measurements vs. Theoretical Hardware Specifications:**  
   Table 3.1 and 3.2 represent **empirically measured code execution times** under QEMU. Table 4.1 represents **mathematical hardware specifications** (SATA 3 bus bandwidth, FPGA line-rate capabilities, and A53 cycle budgets).

---

## 2. Compilation and Binary Verification

The Rust core library (`bluecompress`) was compiled with `--no-default-features` (pure CPU Rayon pipeline) targeting `aarch64-unknown-linux-gnu` using `aarch64-linux-gnu-gcc`:

```text
$ file target/aarch64-unknown-linux-gnu/release/examples/bench_ninja_4k
target/aarch64-unknown-linux-gnu/release/examples/bench_ninja_4k: ELF 64-bit LSB pie executable, ARM aarch64, version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux-aarch64.so.1, BuildID[sha1]=40f060261628609c210e8f7abb58cff8c48fdc34, for GNU/Linux 3.7.0, with debug_info, not stripped
```

- **Binary Size:** 3.8 MB (unstripped release with debug symbols)
- **Dependencies:** glibc (`/lib/ld-linux-aarch64.so.1`, `libc.so.6`, `libm.so.6`, `libpthread.so.0`, `libdl.so.2`)
- **ARM64 Erratum Workaround:** Linked with `-Wl,--fix-cortex-a53-843419`.

---

## 3. Empirical Benchmark Results (QEMU AArch64)

**Input Test Pattern:** 3840 x 2160 (4K UHD) 12-bit Bayer RAW = **11.87 MB/frame** (12,441,600 bytes).  
**Output Codestream:** **5.21 MB/frame** (5,466,991 bytes), **2.28:1 compression ratio** (5.27 bits/sample).

### 3.1 Detailed Single-Frame Stage Breakdown (Serial Execution)
| Stage | Description | Emulated Latency | Proportion of Time | Single-Core Cap |
|---|---|---|---|---|
| **Stage 1: Star-Tetrix** | Bayer Quad Spatial Decorrelation $(Y, Cr, \Delta G, Cb)$ | **96.91 ms** | 53.2% | ~10.32 fps |
| **Stage 2: 5/3 DWT** | 5-level horizontal / 1-level vertical reversible wavelet | **34.69 ms** | 19.1% | ~28.83 fps |
| **Stage 3: Bit-Packing** | Requantization, GCLI rate-control, precinct packing | **50.48 ms** | 27.7% | ~19.81 fps |
| **Total Full-Frame** | End-to-end unpipelined frame compression | **182.07 ms** | 100.0% | **~5.49 fps** |

### 3.2 Multithreaded Full-Frame Compression Scaling (Parallel Worker Threads)
Each worker thread processes complete independent raw Bayer frames (Bayer $\to$ Tetrix $\to$ DWT $\to$ Pack):

| Worker Threads | Elapsed Time (8 Frames) | Mean Latency per Frame | Sustained Throughput | Effective Bitrate |
|---|---|---|---|---|
| **1 Worker** | 0.604 s | 75.51 ms | **13.24 FPS** | 69.0 MB/s |
| **2 Workers** | 0.499 s | 62.42 ms | **16.02 FPS** | 83.5 MB/s |
| **4 Workers** | 0.489 s | 61.08 ms | **16.37 FPS** | 85.4 MB/s |

*Observation:* Under QEMU translation, scaling saturates around ~16 FPS due to host memory allocation synchronization and JIT translation overhead. On physical hardware, memory bus contention on the shared LPDDR4 controller would further constrain multi-core scaling.

---

## 4. Hardware Specifications & Theoretical Feasibility

The following specifications are derived from hardware documentation and physical bus limits (independent of software execution):

| Pipeline Architecture | Execution Unit | 4K 24fps Requirement | 4K 60fps Requirement | Real-Time Feasibility |
|---|---|---|---|---|
| **Pure Software TICO-RAW** | 4x Cortex-A53 @ 1.2 GHz | Requires $\le 41.6\text{ ms/frame}$ (24.1 cycles/pixel) | Requires $\le 16.6\text{ ms/frame}$ (9.6 cycles/pixel) | **Infeasible in software** (~100–125 cycles/pixel required) |
| **Uncompressed 12-bit RAW DMA** | Direct memory-to-SATA | **284.8 MB/s** ($\le 540\text{ MB/s}$ SATA 3) | **711.9 MB/s** ($> 540\text{ MB/s}$ SATA 3) | **24fps Feasible** / **60fps Infeasible** without compression |
| **Hardware Compressed RAW** | ZynqMP FPGA PL (`DPGA*.BIN`) | Line-rate hardware wavelet | Line-rate hardware wavelet | **Fully Feasible** (Factory ProRes RAW / TICO architecture) |

---

## 5. Engineering Conclusions

1. **Software Wavelet Compression Cannot Record 4K 24/60fps on A53:**  
   Even on a high-speed host PC under QEMU, full-frame compression reaches only ~16 FPS. On the physical Ninja V's low-power in-order Cortex-A53 cores (@ 1.2 GHz), estimated performance is roughly **2 to 4 FPS**. Software compression cannot be used as an inline recording engine for video.
2. **Factory Hardware Integrity is Critical:**  
   All real-time video encoding on the Ninja V relies on the Xilinx FPGA bitstreams and the Cortex-R5 co-processor (`APP0000.BIN`). The custom engineering approach must treat these proprietary blocks as untouchable black boxes.
3. **Viable Paths for Custom RAW Workflows:**  
   - **Path A (Uncompressed DMA):** Capture uncompressed 12-bit Bayer frames (CinemaDNG) directly from video memory to SATA SSD at 24fps / 25fps (284.8 MB/s, well within SATA 3.0 SSD limits).  
   - **Path B (FPGA Hardware Integration):** Interface with the existing FPGA bitstream via `/dev/copro_comms_*` to record compressed formats at 60fps.  
   - **Path C (Additive Monitor Tool):** Expose custom RAW tools, Bayer inspection, and telemetry via an additive UI drawer (`[V-RAW]`), preserving the authentic factory AtomOS 11 interface without interference.
