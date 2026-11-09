# Phase 1 — Service & Driver Inventory (AtomOS 11.19.00)

> [!IMPORTANT]
> **Revision 2 — evidence-based rewrite.** Every size, hash and string below was extracted directly from `rootfs_ext4` by `tools/phase1_evidence.py`. See [phase1_corrections.md](documentation/findings/phase1_corrections.md).

## 1. Atomos Linux Services (`/usr/bin/`) — VERIFIED

| Binary | Size (bytes) | SHA-256 (first 16) | Key dependencies | Inter-process communication / device paths found in strings |
|---|---:|---|---|---|
| `video_pipeline` | 2,879,712 | `b2a99dd9d834dc82…` | `libgstreamer-1.0`, `libgstapp-1.0`, `libgstvideo-1.0`, `libgstallocators-1.0`, `libgstcodecparsers-1.0`, `libgstaudio-1.0`, `libndi.so.6`, `libprotobuf.so.32`, `libevent-2.1`, `libcurl`, `libssl`, `libasound` | `/dev/copro_comms_data`, `/dev/dma_heap`, `/dev/mem`. Negotiates GStreamer elements: `omxh264enc`, `omxh265enc`, `qtmux`, `srtsink`, `rtmp2sink`. String hits for pixel formats: `nv12`, `nv16_10le32`, `video/x-raw`. Strings also contain `ProRes` and `Bayer` (see analysis below). |
| `streaming_pl` | 2,879,712 | `395f0f366b663f18…` | (same as `video_pipeline`) | Same binary size and dependencies as `video_pipeline`, but uses `/dev/copro_comms_data` with streaming-focused defaults (`ENC_EXTRA_OP_BUFFERS=10` in init script). |
| `core_control` | 727,328 | `64f5c291253a5f34…` | `libprotobuf.so.32`, `libndi.so.6`, `libevent-2.1` | `/dev/copro_comms_ctrl`, `/dev/mmcblk0`, `/sys/class/net/`. Starts/stops services, manages network and partition migrations. |
| `cloud_service` | 3,730,872 | `70af379e244b29d4…` | `libcurl`, `libssl`, `libgstreamer-1.0`, `libuuid`, `libprotobuf.so.32` | `/dev/copro_comms_app3`, `/dev/dma_heap`. Handles Frame.io / Atomos Cloud chunk uploads. |
| `media_control` | 266,816 | `d4ddf2016909f5e5…` | `libprotobuf.so.32`, `libevent-2.1` | `/dev/copro_comms_app4`, `/sys/class/mmc_host/mmc1`, `/sys/kernel/config/device-tree/overlays/sd`. Manages storage cards/SSDs. String hit: `Attached RAW disk driver `. |
| `camera_control` | 266,432 | `aaab07983e634317…` | `libCr_Core.so`, `libprotobuf.so.32`, `libevent-2.1` | `/dev/copro_comms_app5`. Remote camera control via Sony Camera Remote SDK (`libCr_Core.so`) and others. |
| `audio_encoder` | 266,912 | `d0b9be81ed8fa1c8…` | `libgstreamer-1.0`, `libprotobuf.so.32`, `libcurl` | `/dev/copro_comms_app5`, `/dev/dma_heap`. Audio encoding service. |
| `talkback_pl` | 464,784 | `8fd9166a972a48e8…` | `libgstreamer-1.0`, `libasound`, `libprotobuf.so.32` | `/dev/copro_comms_app5`, `/dev/snd/controlC0`, `/dev/dma_heap`. |
| `ctrlsw_encoder` | 1,839,072 | `472bff601cf1f031…` | `libc`, `libstdc++` | `/dev/allegroIP` (Xilinx VCU hardware encoder driver). |
| `ctrlsw_decoder` | 657,824 | `08f471049db5cc8c…` | `libc`, `libstdc++` | `/dev/allegroDecodeIP` (Xilinx VCU hardware decoder driver). |

## 2. Kernel Modules (`/lib/modules/6.1.5-xilinx-v2023.1/extra/`) — VERIFIED

| Module | Size | Description (from modinfo) | Author / Notes |
|---|---:|---|---|
| `copro-comms.ko` | 24,184 | message and buffer sharing between co-processors | Austin Boyle (Atomos). Compatible `atomos,copro-comms`. Provides `/dev/copro_comms_*`. |
| `copro-buf-exporter.ko` | 15,368 | Co-processor buffer exporter | Austin Boyle (Atomos). Exports buffers as dma-buf. |
| `custom-cma.ko` | 17,776 | view & modify CMA pools from user space | Austin Boyle (Atomos). Compatible `atomos,custom-cma`. |
| `ipi-mbox.ko` | 12,944 | IPI messaging mailbox | Austin Boyle (Atomos). ZynqMP hardware mailbox. |
| `pl-audio.ko` | 20,224 | loadable audio module | Graham Gallagher (Atomos). Compatible `atomos,pl-audio`. |
| `pl-irq.ko` | 10,488 | IRQ Chip driver for atomos PL IRQ | Adrian (Atomos). Compatible `atomos,pl-irq`. |
| `pl-sata.ko` | 17,864 | Custom DG core SATA3 driver | Jordan Boekel (Atomos). Compatible `atomos,pl-sata` (status in system.dts: `disabled`). |
| `pl-sysreg.ko` | 14,808 | Atomos Sysreg Userspace I/O driver | Austin Boyle (Atomos). |
| `al5e.ko` | 24,176 | Allegro Codec Driver (encoder) | Allegro / Xilinx VCU |
| `al5d.ko` | 22,624 | Allegro Codec Driver (decoder) | Allegro / Xilinx VCU |
| `allegro.ko` | 68,312 | Allegro Common | Allegro / Xilinx VCU |
| `dmaproxy.ko` | 14,080 | Xilinx's zynqmp-dma Client Driver | Xilinx (loaded via `modules-load.d/dmaproxy.conf`) |

## 3. Communication Channels Between Linux and R5 — VERIFIED

The device tree defines six communication nodes (`system.dts` lines 1668–1708), each paired with an IPI mailbox channel:

| Node name | Driver | Character device created | User-space client |
|---|---|---|---|
| `ipi_data_ch` | `atomos,copro-comms` | `/dev/copro_comms_data` | `video_pipeline`, `streaming_pl` |
| `ipi_cntrl_ch` | `atomos,copro-comms` | `/dev/copro_comms_ctrl` | `core_control` |
| `ipi_app2_ch` | `atomos,copro-comms` | `/dev/copro_comms_app2` | (available for streaming / secondary pipeline) |
| `ipi_app3_ch` | `atomos,copro-comms` | `/dev/copro_comms_app3` | `cloud_service` |
| `ipi_app4_ch` | `atomos,copro-comms` | `/dev/copro_comms_app4` | `media_control` |
| `ipi_app5_ch` | `atomos,copro-comms` | `/dev/copro_comms_app5` | `camera_control`, `audio_encoder`, `talkback_pl` |

All services use `libprotobuf.so.32` and `libevent-2.1`. The protocol messages over these channels are structured Protobuf payloads.

## 4. What this means for custom RAW recording

- **VERIFIED:** Linux `video_pipeline` is primarily a GStreamer + Xilinx VCU wrapper for H.264/H.265 encoding, RTMP/SRT streaming and NDI.
- **VERIFIED:** `video_pipeline` receives video metadata and frame notifications over `/dev/copro_comms_data` from the R5 processor.
- **VERIFIED:** The word `Bayer` and `ProRes` exist in `video_pipeline` strings, but they appear in capability / mode tables, not in any GStreamer raw-Bayer processing pipeline.
- **UNKNOWN:** We do **not** know whether raw 12-bit Bayer frames are ever exposed in `codec_input` (`0x1b000000`, 272 MiB) when recording in ProRes RAW mode, or if that memory region is only used when the VCU / Linux pipeline is active. This remains the central question to answer in Phase 3.
