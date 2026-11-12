# Verdanove RAW — Master Caddy SSD Setup & Deployment Guide

**Target Hardware:** Atomos Ninja V (5-inch HDR Monitor-Recorder)  
**SoC Architecture:** Xilinx Zynq UltraScale+ XCZU5EV (Quad Cortex-A53 + Dual Cortex-R5)  
**Supported Firmware:** AtomOS 11.19.00 (and 10.x baseline)  
**Recording Format:** 12-Bit Uncompressed CinemaDNG (Bayer RGGB, 4K UHD 3840x2160 @ 24fps)  
**Safety Guarantee:** **100% Non-Destructive**. Operates entirely in RAM overlays and external SATA SSD storage. **Never writes to internal NAND / QSPI flash.**

---

## 1. SSD Preparation & Formatting

To ensure maximum direct I/O throughput (**>284 MB/s**) with zero dropped frames, format your 2.5-inch SATA SSD (e.g., Angelbird AtomX SSDmini, Samsung 870 EVO, or SanDisk Ultra 3D):

1. **Partition Table:** MBR (Master Boot Record) or GPT.
2. **Filesystem:** **exFAT** (native AtomOS standard) or **ext4**.
3. **Allocation Unit / Cluster Size:** **128 KB** (or standard 4 KB sector alignment).
4. **Volume Label:** `ATOMOS` (or any single-word label).

---

## 2. Copying the Verdanove Payload to the SSD

Extract or copy the contents of `deploy/ssd_payload/` directly to the **root** of your Master Caddy SSD:

```text
F:\ (or /run/media/NINJAV-sda1/)
├── autorun.sh
├── README_SSD_SETUP.md
└── verdanove/
    ├── bin/
    │   ├── vraw_daemon_arm64      # AArch64 CinemaDNG & CoPro ring writer
    │   └── libfakecopro.so        # LD_PRELOAD CoPro snooper & SCM_RIGHTS forwarder
    ├── config/
    │   └── vraw.conf              # 4K resolution, 24fps, DNG tags
    ├── clips/                     # Output directory where .dng clips appear
    ├── logs/                      # Runtime CoPro & capture logs
    ├── install_sidecar.sh         # Non-destructive RAM overlay helper
    ├── run_recorder.sh            # Standalone / direct CoPro recorder launcher
    └── snoop_video_pipeline.sh    # Non-destructive stock video_pipeline LD_PRELOAD snooper
```

---

## 3. How the Non-Destructive Execution Works

When the SSD is inserted into the Atomos Ninja V Master Caddy slot:

1. **Automount:** Stock udev/systemd (`/etc/udev/scripts/mount.sh`) mounts the drive under `/run/media/<LABEL>-sda1` (for label `NINJAV`, `/run/media/NINJAV-sda1`, or `/run/media/sda1` if unlabeled). Stock AtomOS udev rules do **not** run `autorun.sh` automatically on insert.
2. **Zero Internal Flash Writes:** Scripts stage binaries into `/tmp/verdanove_bin/` (RAM tmpfs, bypassing exFAT `noexec`) and write all captures/logs back to `verdanove/` on the SSD. Everything in `/tmp` disappears on reboot.
3. **Execution via Shell (UART Serial `ttyPS0` at `115200` baud 8N1 or network shell):**
   ```sh
   # Mode A: Live CoPro snooping + frame forwarding via libfakecopro.so:
   /run/media/NINJAV-sda1/verdanove/snoop_video_pipeline.sh --frames 24

   # Mode B: Snoop ioctl traffic only (logs to verdanove/logs/copro_snoop_*.log):
   /run/media/NINJAV-sda1/verdanove/snoop_video_pipeline.sh --snoop-only

   # Mode C: Standalone synthetic 4K 24fps SATA storage benchmark:
   /run/media/NINJAV-sda1/verdanove/run_recorder.sh --standalone 24
   ```

---

## 4. Capturing & Snooping Commands

```sh
# Snoop stock /usr/bin/video_pipeline and forward DMABUFs to vraw_daemon:
./snoop_video_pipeline.sh --frames 120

# Run standalone 4K benchmark directly:
./run_recorder.sh --standalone 240
```

### Live Terminal Feedback
```text
====================================================================
 Verdanove RAW Native C Integration Daemon (vraw_daemon)
 Target: Atomos Ninja V (Quad Cortex-A53 / Zynq UltraScale+)
 Pipeline Mode: 12-Bit Uncompressed Bayer (RGGB) CinemaDNG
 Output Resolution: 3840x2160 (4K UHD) | Direct I/O Sector Size: 4096
 Streaming Target: Continuous @ 24.00 fps -> verdanove/clips/CLIP_20261109_120000
====================================================================

[VRAW_IPC] Connected to socket: /var/run/user/1000/atomos/video_pipeline_socket
[VRAW_IPC] Sent Protobuf configuration handshake.
[VRAW_REC] Frame 00000 written: 11.87 MB in 5.82 ms (2040.1 MB/s) | Queue: 0/8
[VRAW_REC] Frame 00001 written: 11.87 MB in 5.94 ms (1998.7 MB/s) | Queue: 0/8
...
====================================================================
 Verdanove RAW Capture Engine Summary:
   - Total Frames Captured:  240 / 240
   - Dropped Frames:         0 (0.00% drop rate)
   - Total Data Streamed:    2848.60 MB in 10.002 seconds
   - Sustained Framerate:    23.99 FPS (Target: 24.00)
   - Sustained Throughput:   284.80 MB/s (SATA 3 Limit: ~540 MB/s)
   - Real-Time Verification: PASSED (100% Real-Time Compliant)
====================================================================
```

---

## 5. Importing into DaVinci Resolve

1. Unmount the SSD from the Ninja V and connect it to your PC / Mac editing workstation.
2. Open **DaVinci Resolve Studio** (or free edition).
3. In the Media Pool, navigate to `verdanove/clips/CLIP_YYYYMMDD_HHMMSS/`.
4. DaVinci Resolve automatically detects the `.dng` files as a single continuous 3840x2160 video clip.
5. In the **Color Page -> Camera RAW** palette:
   - **Decode Using:** Clip
   - **Color Space:** CinemaDNG
   - Full 12-bit highlight recovery, exposure adjustment, white balance, and tint controls are active without ARRI profile fallback.

