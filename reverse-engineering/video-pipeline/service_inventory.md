# Phase 1 Deliverable: Recording, Video Pipeline & Service Inventory (`ATOMNJV.FW` — AtomOS 11.19.00)

- **Project:** Verdanove Ninja Lab
- **Target Device:** Original Atomos Ninja V (5-inch model)
- **Firmware Baseline:** AtomOS `11.19.00` (`ATOMNJV.FW`)

---

## 1. System Initialization & Boot Sequence (`/etc/inittab` -> `/etc/init.d/atomos-init`)

AtomOS 11.19.00 uses **SysVinit** (`/sbin/init.sysvinit`, default runlevel `5`). The primary orchestration script is `/etc/init.d/atomos-init` (`S99atomos-init`), which executes the following deterministic startup pipeline:

1. **Mount Persistent Storage:**
   - Mounts `/dev/mmcblk0p1` at `/boot` (FAT16 partition holding `DPGA00XX.BIN`, `APP0000.BIN`, `RES0001.BIN`).
   - Mounts `/dev/mmcblk0p3` at `/atomos` (`ext4` persistent configuration & logs).
2. **Load Custom Kernel Modules (`insmod` / `modprobe`):**
   - `ipi-mbox.ko` — ZynqMP Inter-Processor Interrupt (IPI) hardware mailbox driver (`0xff310000`) for Cortex-A53 <-> Cortex-R5 signaling.
   - `copro-comms.ko` — Creates 6 character devices (`/dev/copro_comms_data`, `/dev/copro_comms_ctrl`, `/dev/copro_comms_app2`..`app5`) mapped over shared DDR memory and IPI interrupts.
   - `copro-buf-exporter.ko` — Zero-copy `dma_buf` exporter (`/dev/copro_buf_exporter`) that wraps physical frame buffers in `codec_input` (`0x1b000000`–`0x2c000000`, `272 MiB`) into Linux `dma_buf` file descriptors for VCU and GStreamer.
   - `custom-cma.ko` — Dynamic CMA pool manager (`/sys/devices/platform/custom_cma/resize`) managing `codec_output` (`0x2c000000`–`0x60000000`, `832 MiB`).
   - `al5e.ko` & `al5d.ko` — Xilinx/Allegro DVT Video Codec Unit (VCU) H.264/H.265 hardware encoder (`/dev/allegroIP`) and decoder (`/dev/allegroDecodeIP`).
3. **Boot the Cortex-R5 Real-Time Co-Processor (`/usr/bin/start_r5.sh`):**
   - Loads `RES0001.BIN` (`startrek.resource_pack.p32`) into DDR at `0x44000000`.
   - Loads `APP0000.BIN` (`startrek_noresources.elf`) into R5 DDR (`0x60000000`–`0x80000000`) via Linux `remoteproc` (`/sys/class/remoteproc/remoteproc0/state`) or ZynqMP PMU/FSBL handoff.
4. **Launch Userspace Daemons:**
   - Starts `core_control`, `video_pipeline`, `streaming_pl`, `cloud_service`, `media_control`, `camera_control`, `audio_encoder`, and `talkback_pl`.

---

## 2. Co-Processor IPC Channels (`/dev/copro_comms_*`)

All communication between the **Cortex-R5 ("CoPro", running `APP0000.BIN`)** and **Linux userspace on the quad-core Cortex-A53** flows through 6 dedicated character devices provided by `copro-comms.ko`:

| Device Node | Linux Daemon(s) | Direction & Protocol Role |
|---|---|---|
| `/dev/copro_comms_ctrl` | `/usr/bin/core_control` | System management, dynamic FPGA bitstream switching (`load_fpga.sh`), CMA memory resizing (`init_mem_layout.sh`), network/Wi-Fi/Ethernet control, firmware updates, and thermal/power status |
| `/dev/copro_comms_data` | `/usr/bin/video_pipeline` | Primary Linux video recording/playback IPC channel: receives frame buffer descriptors (physical offsets in `codec_input` `0x1b000000`), codec parameters, timecode, and audio packets from R5; returns encoded bitstream buffers or decoded frames |
| `/dev/copro_comms_app2` | `/usr/bin/streaming_pl` | Dedicated secondary video pipeline channel for live streaming (RTMP, SRT, NDI HX2/HX3) running concurrently with recording |
| `/dev/copro_comms_app3` | `/usr/bin/cloud_service` | Atomos Cloud Studio / Frame.io Camera-to-Cloud (C2C) upload queue, progressive MP4/MOV proxy chunk transfer, and cloud pairing |
| `/dev/copro_comms_app4` | `/usr/bin/media_control` | External media / storage management (USB-C / SATA SSD indexing, exFAT formatting/repair via `exfatprogs`, file deletion, clip directory queries) |
| `/dev/copro_comms_app5` | `/usr/bin/camera_control`, `/usr/bin/audio_encoder`, `/usr/bin/talkback_pl` | Multiplexed application channel for LANC/USB/Bluetooth/IP camera control, AAC audio encoding (`libfdk-aac`), and cloud talkback audio |

---

## 3. Deep-Dive Inventory of Atomos Linux Services

| Service Binary | Size (Bytes) | SHA-256 | Linked Libraries & Frameworks | Detailed Technical Responsibilities |
|---|---:|---|---|---|
| `/usr/bin/video_pipeline` | `597,688` | `6f4b9044dc79cf974c245992d62fd935f12c276bc96c06401f74452cf6f94e87` | `libgstreamer-1.0.so.0`, `libgstapp-1.0.so.0`, `libgstvideo-1.0.so.0`, `libgstpbutils-1.0.so.0`, `libstdc++.so.6` | **Linux Video Recording, Playback & Transcode Daemon.** Communicates via `/dev/copro_comms_data` and imports zero-copy DMA buffers via `/dev/copro_buf_exporter`. Builds GStreamer pipelines using `omxh264enc`, `omxh265enc`, `omxh264dec`, `omxh265dec` (Xilinx VCU via OpenMAX IL `libgstomx.so`), `qtmux` (`.mov`), `matroskamux` (`.mkv`), `mp4mux` (`.mp4`), or raw YUV `appsink`/`filesink`. |
| `/usr/bin/streaming_pl` | `597,688` | `35f3996b59985ef388fd42173c0cf034f57098718d3706716a736bf614585850` | Same as `video_pipeline` + `libndi.so.5`, `librtmp.so.1`, `libsrt.so.1.4` | **Live Streaming Daemon.** Compiled from the same C++ source tree as `video_pipeline` (`src/pipeline/`), bound to `/dev/copro_comms_app2`. Drives NDI (`ndisink`), RTMP (`rtmp2sink`), and SRT (`srtsink`) streams using the VCU secondary encode stream. |
| `/usr/bin/core_control` | `462,840` | `848f1823ebbd38f48bc3bd569820bf8e28bf91e95679b0b6959dc550fd423fb2` | `libnm.so.0`, `libglib-2.0.so.0`, `libgio-2.0.so.0`, `libstdc++.so.6` | **System & Hardware Supervisor Daemon.** Listens on `/dev/copro_comms_ctrl`. Executes `/etc/init.d/load_fpga.sh <type_id>` when the user switches recording codecs on the Ninja V UI, executes `/etc/init.d/init_mem_layout.sh` to resize CMA (`codec_output`), manages NetworkManager (`nmcli`), NTP (`chronyd`), and expansion module firmware updates (`FMOD*`/`XMOD*`). |
| `/usr/bin/cloud_service` | `1,301,608` | `520102ff1a4ff6f8028f2f53a4a2c0cf8220dc9b4528d5b07c7d1007fa4924c7` | `libcurl.so.4`, `libssl.so.3`, `libcrypto.so.3`, `libarchive.so.13` | **Atomos Cloud Studio / Frame.io C2C Daemon.** Listens on `/dev/copro_comms_app3`. Handles HTTPS/TLS REST APIs, S3 multipart uploads of growing `.mp4`/`.mov` proxy files (`progressive_upload`), and device registration. |
| `/usr/bin/media_control` | `234,048` | `9bd84eb70c30482b6f6a3f0392363414c70a76df160fc19853b9ef8452dc66a2` | `libudev.so.1`, `libblkid.so.1`, `libmount.so.1` | **Storage & Filesystem Daemon.** Listens on `/dev/copro_comms_app4`. Monitors SATA/USB storage hotplug events, mounts/unmounts media, formats drives (`mkfs.exfat`), and provides filesystem metadata to the Cortex-R5 when Linux-side recording/C2C is active. |
| `/usr/bin/camera_control` | `781,160` | `30a2b2908ec6201f373ee129d282f702446df9e4bd50372821c0371cb0a66727` | `libusb-1.0.so.0`, `libbluetooth.so.3`, `libglib-2.0.so.0` | **Camera Control Daemon.** Listens on `/dev/copro_comms_app5`. Implements PTP/IP, USB PTP, and Bluetooth LE camera control protocols (record trigger, ISO, shutter, aperture, white balance) for supported cameras (Sony, Canon, Nikon, Panasonic, Fujifilm, Z CAM). |
| `/usr/bin/audio_encoder` | `72,000` | `20df3c6744bf7a23042862d054829c3f1a7122773982166957c858df1a17b84b` | `libfdk-aac.so.2`, `libstdc++.so.6` | **AAC Audio Encoder Service.** Receives raw PCM audio buffers from Cortex-R5 over `/dev/copro_comms_app5`, encodes to AAC-LC using `libfdk-aac`, and returns compressed AAC frames for MP4/RTMP/SRT muxing. |
| `/usr/bin/talkback_pl` | `141,944` | `34625a170c473802f7958b35e7304143905310366c8861e61a9659761fc95670` | `libgstreamer-1.0.so.0`, `libgstaudio-1.0.so.0` | **Bidirectional Audio Talkback Service.** GStreamer-based opus/AAC audio streaming pipeline for Atomos Cloud Studio live talkback. |

---

## 4. Deep Inspection of `/usr/bin/video_pipeline` & Pixel Formats

Static symbol and string analysis of `/usr/bin/video_pipeline` (`597,688` bytes, C++17, unstripped dynamic symbols + detailed logging strings) reveals how Linux interacts with video frames:

### 4.1 Internal C++ Classes Identified in `video_pipeline`
- `CoProComms` / `CoProDataChannel` (`/dev/copro_comms_data`)
- `CoProBufExporter` (`/dev/copro_buf_exporter`, ioctl wrapper exporting physical pages from `0x1b000000` `codec_input` as `dma_buf` FDs)
- `PipelineManager`
- `RecordPipeline` (`qtmux`, `mp4mux`, `matroskamux`, `filesink`)
- `PlaybackPipeline` (`qtdemux`, `matroskademux`, `omxh264dec`, `omxh265dec`)
- `StreamPipeline` (`rtmp2sink`, `srtsink`, `ndisink`)
- `YuvCapturePipeline` / `YuvPassThrough`

### 4.2 Supported Pixel Formats in `video_pipeline`
Strings extracted from `video_pipeline` format negotiation tables:
- `nv12` (8-bit 4:2:0 semi-planar YUV)
- `nv16` (8-bit 4:2:2 semi-planar YUV)
- `nv16_10le32` / `10b422` (Xilinx VCU 10-bit 4:2:2 packed format: 3 pixels in each 32-bit word, `XV20`)
- **Important Observation for RAW Research:**
  - `video_pipeline` contains **no references** to ProRes, ProRes RAW, DNxHR, DNxHD, or 12-bit Bayer RAW formats (`rggb`, `bggr`, `bayer`, `12bit`).
  - Why? Because **ProRes, ProRes RAW (`DPGA0005.BIN` / `DPGA0012.BIN`), and DNxHR (`DPGA0003.BIN`) are encoded directly by the ZynqMP FPGA Programmable Logic (PL) and written to the SATA SSD by the Cortex-R5 (`APP0000.BIN`)**, completely bypassing Linux `video_pipeline`!
  - Linux `video_pipeline` is only invoked when the FPGA is loaded with an H.265/VCU or streaming bitstream (`DPGA0009.BIN`, `DPGA0013.BIN`, `DPGA0017.BIN`–`DPGA0020.BIN`), where the FPGA DMA-transfers uncompressed frames into `codec_input` (`0x1b000000`–`0x2c000000`) and hands frame descriptors to `video_pipeline` via `/dev/copro_comms_data`.

---

## 5. Dynamic Memory & FPGA Switching Scripts (`/etc/init.d/`)

### 5.1 `/etc/init.d/init_mem_layout.sh`
Dynamically resizes the Linux CMA pool (`codec_output` at `0x2c000000`, up to `832 MiB`) via `/sys/devices/platform/custom_cma/resize` depending on the active operating mode:
- `mode 0` (Idle / ProRes / DNx / ProRes RAW — FPGA/R5 uses DDR directly, Linux VCU unused): shrinks Linux CMA to free DDR for R5.
- `mode 1` (H.265 Record / Playback via VCU): expands Linux CMA pool so `al5e`/`al5d` can allocate 4K60 10-bit reference and bitstream buffers.

### 5.2 `/etc/init.d/load_fpga.sh`
Invoked by `core_control` when the Cortex-R5 requests an FPGA reconfiguration:
1. Reads current FPGA bitstream `type_id` from physical register `0x820010DC` using `/usr/bin/load_fpga` (`devmem`).
2. Maps requested mode ID (`0x00`..`0x14`) to `/boot/DPGA00XX.BIN`.
3. Writes the encrypted ZynqMP bitstream via the ZynqMP FPGA Manager (`/sys/class/fpga_manager/fpga0/firmware`), which passes the bitstream to the PMU/CSU hardware AES-GCM engine (`EFUSE_RED_KEY`) to reconfigure the PL fabric in milliseconds.
