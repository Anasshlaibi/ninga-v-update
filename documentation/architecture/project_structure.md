# Verdanove Ninja Lab — Project Structure

```text
verdanove-ninja-lab/
├── README.md
├── environment_report.md
├── firmware_manifest.json
├── SHA256SUMS
├── project_structure.md
├── .gitignore
│
├── firmware/
│   ├── original/                 # Immutable read-only ATOMNJV.FW (AtomOS 11.19.00)
│   ├── extracted/                # Isolated extraction workspace for Phase 1
│   ├── metadata/                 # firmware_manifest.json & header metadata
│   ├── hashes/                   # SHA256SUMS & integrity manifests
│   └── release_notes/            # Official Atomos release notes & documentation
│
├── reverse-engineering/
│   ├── container-analysis/       # Outer firmware container layout, offsets & checksums
│   ├── filesystem/               # FAT boot partitions & PetaLinux rootfs maps
│   ├── bootloader/               # FSBL, PMUFW, ATF, and U-Boot environment analysis
│   ├── device-tree/              # Extracted .dtb and decompiled .dts Device Tree sources
│   ├── binaries/                 # ELF binary inventory, symbols, and dependency graphs
│   ├── video-pipeline/           # Static analysis of video_pipeline & codec libraries
│   └── fpga/                     # Zynq UltraScale+ PL bitstreams & MAX 10 images
│
├── hardware/
│   ├── component-identification/ # Verified ICs (MPSoC, MAX 10, EFM32, PMICs, PHYs)
│   ├── pcb-research/             # Board topology, UART/JTAG headers, power rails
│   ├── interfaces/               # HDMI 2.0 receiver path, AtomX expansion bus
│   ├── storage/                  # Master Caddy II / AtomX SSDmini SATA interface
│   ├── memory/                   # DDR4 configuration, bandwidth, and CMA allocations
│   └── compute/                  # Cortex-A53/A72 cores, Mali-400 MP2, VCU capabilities
│
├── compression/
│   ├── blue-compressor/          # Blue Compressor architecture & source evaluation
│   ├── tico-raw/                 # TICO-RAW / JPEG XS Bayer compression evaluation
│   ├── r3d-ne/                   # Nikon R3D NE container & Bayer data analysis
│   ├── arm64-port/               # Standalone Linux AArch64 port & NEON optimizations
│   ├── gpu-benchmarks/           # Workstation RTX 4060 & embedded accelerator tests
│   └── cpu-benchmarks/           # Host & ARM64 CPU throughput, latency, and memory tests
│
├── recording-engine/
│   ├── input/                    # Frame ingestion & HDMI/RAW signal validation
│   ├── processing/               # Bayer packing, bit-depth validation, and buffering
│   ├── encoding/                 # Compression worker pool & real-time scheduler
│   ├── storage/                  # Direct I/O SSD writer & ring-buffer management
│   ├── metadata/                 # Timecode, camera metadata, WB/ISO & audio tracks
│   └── verification/             # Frame-drop detection & post-record integrity checks
│
├── interface/
│   ├── monitoring/               # Coexistence with native AtomOS scopes & LUTs
│   ├── recording-controls/       # Trigger, tally, and status integration
│   ├── compression-settings/     # Lossless/lossy ratio presets & bitrate targets
│   └── diagnostics/              # Honest bit-depth badge, temperature, SSD throughput
│
├── tests/
│   ├── firmware/                 # Container parsing & checksum verification tests
│   ├── codec/                    # PSNR/SSIM/bit-exactness tests on Bayer CFA frames
│   ├── performance/              # Sustained frame-rate & memory pressure tests
│   ├── compatibility/            # DaVinci Resolve & REDCINE-X PRO ingest verification
│   └── recovery/                 # Power-loss & dual-bank bootloader recovery procedures
│
└── documentation/
    ├── architecture/             # System & integration design specifications
    ├── findings/                 # Phase-by-phase reverse-engineering reports
    ├── benchmarks/               # Empirical performance datasets & charts
    ├── risks/                    # Hardware, thermal, legal, and bricking risk register
    ├── installation/             # Toolchain setup & firmware preservation checklists
    └── changelog/                # Milestone logs
```
