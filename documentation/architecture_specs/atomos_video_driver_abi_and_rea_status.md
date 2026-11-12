# AtomOS Ninja V Video Driver ABI Trace & REA Setup Report

**Target Platform:** Atomos Ninja V (Xilinx Zynq UltraScale+ MPSoC `XCZU5EV` / AArch64 Linux `6.1.5-xilinx-v2023.1`)  
**Firmware Analyzed:** AtomOS `11.19.00` (non-destructively extracted into `firmware/extracted/rootfs_ext4/` and `reverse-engineering/device-tree/system.dts`)  
**Companion C Bindings:** [`recording-engine/atomos_copro_abi.h`](../../recording-engine/atomos_copro_abi.h)

> **Non-Destructive Verification:** [`firmware/original/ATOMNJV.FW`](../../firmware/original/ATOMNJV.FW) remains unmodified (`SHA-256: 65e14e67bcc2624115300624d967634042601f23e9574e75ee7f06f2c8004be1`).

---

## 1. REA / Ghidra MCP Environment Status & Tooling Attribution

### 1.1 `tools/rea/` Setup Verification (WSL Ubuntu 24.04)
`https://github.com/morluto/rea.git` (`rea-agents@6.8.0`, commit `047d75a498f18a6608f35ee5e36cf1bf0f81ca97`) is built and healthy in [`tools/rea/`](../../tools/rea/) inside the WSL Ubuntu 24.04 x86_64 toolchain environment (`npm run build:cached`: `3 successful, 3 total`):

| Dependency / Check | Configured Toolchain (WSL Ubuntu 24.04) | REA Requirement | Verdict |
|---|---|---|---|
| `node` | `v24.22.3` (`~/.local/opt/node-v24.22.3-linux-x64/bin/node`) | `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` | **Healthy** |
| `java` (`JAVA_HOME`) | OpenJDK `21.0.13` (`~/.local/opt/jdk-21`) | 64-bit JDK 21+ | **Healthy** |
| `ghidra` (`GHIDRA_INSTALL_DIR`) | Ghidra `12.1.4` (`~/.local/opt/ghidra_12.1.4_PUBLIC`) | Ghidra 12.x (`>=12.1`) | **Healthy** |
| `ghidra-headless` / `native_decompiler` | `support/analyzeHeadless` + `os/linux_x86_64/decompile` | Headless project + AArch64 C decompiler | **Healthy** |
| `rea doctor --provider ghidra --json` | `"healthy": true`, `"configured": true`, `"available": true` (`6.8.0`, `196` CLI / `255` MCP tools) | Ghidra provider readiness | **Passed** |
| Cross & host compilers | `gcc`, `aarch64-linux-gnu-gcc`, `aarch64-linux-gnu-g++` | Host + AArch64 ELF builds | **Available** |

> **Scope note (`tools/rea` CLI vs IDE host MCP):** All Ghidra decompilation queries (`ghidra_decompile`, `ghidra_search`, `ghidra_xrefs`, `inspect-native-load-image`, `decompile-all`) ran cleanly via `tools/rea` inside WSL with 8 binary analysis checkpoints cached under `~/.local/share/rea-checkpoints` (for `video_pipeline`, `sha256: b2a99dd9d834dc82b5373e159957aa3b5d4e2b1c2ea5545feb76d78dd14f671f`, `language_id: "AARCH64:LE:64:v8A"`, `image_base: "0x100000"`). Note that REA checks `GHIDRA_INSTALL_DIR` (not `GHIDRA_INSTALL_PATH`).

### 1.2 Combined Static & Decompiler Methodology
- **Ghidra 12.1.4 + REA (`6.8.0`):** Used to decompile [`/usr/bin/video_pipeline`](../../firmware/extracted/rootfs_ext4/usr/bin/video_pipeline) (rebased at `0x100000` in Ghidra; ELF VMA offsets correspond to `Ghidra VA - 0x100000`), probe `/usr/bin/core_control` and `/usr/bin/media_control`, and decompile the unstripped kernel modules (`copro-comms.ko`, `copro-buf-exporter.ko`, `custom-cma.ko`, `pl-sysreg.ko`, `al5e.ko`, `dmaproxy.ko`).
- **GNU Binutils / ELF Inspection:** `aarch64-linux-gnu-objdump`, `readelf`, `file`, and `strings` cross-checked PIE virtual offsets, PLT stubs, and shared-library calls (`libgstallocators-1.0.so.0.2005.0`).

---

## 2. Target Binary Discovery & ELF Architecture Verification

Inspection of [`reverse-engineering/binaries/binary_inventory.csv`](../../reverse-engineering/binaries/binary_inventory.csv), [`reverse-engineering/video-pipeline/service_inventory.md`](../../reverse-engineering/video-pipeline/service_inventory.md), and [`firmware/extracted/rootfs_ext4/`](../../firmware/extracted/rootfs_ext4/) confirms the core video/CoPro daemons and kernel modules are `ELF64` AArch64 Little-Endian:

| Artifact Path (in `rootfs_ext4`) | ELF Class / Endianness / Type | Machine | Interpreter / BuildID (`sha1`) | Strip State & Role |
|---|---|---|---|---|
| `/usr/bin/video_pipeline` | `ELF64` LSB `ET_DYN` (PIE) | `AArch64` | `/lib/ld-linux-aarch64.so.1` / `1a5facc1ae3ecbf76a050e8294e27ae08b31edc8` | Stripped (`2,879,712` B); primary video/GStreamer/VCU daemon (`/dev/copro_comms_data`) |
| `/usr/bin/streaming_pl` | `ELF64` LSB `ET_DYN` (PIE) | `AArch64` | `/lib/ld-linux-aarch64.so.1` / `1a5facc1ae3ecbf76a050e8294e27ae08b31edc8` | Stripped (`2,879,712` B); launched with `--comms=/dev/copro_comms_app2` per init script |
| `/usr/bin/core_control` | `ELF64` LSB `ET_DYN` (PIE) | `AArch64` | `/lib/ld-linux-aarch64.so.1` / `62dc7e4691549ce85f5ac852feb51c9c3b41b8b9` | Stripped; master system/CoPro control service (`/dev/copro_comms_ctrl`) |
| `/usr/bin/media_control` | `ELF64` LSB `ET_DYN` (PIE) | `AArch64` | `/lib/ld-linux-aarch64.so.1` / `50b3908ec65b84040b336011b5552ce96c1fdfed` | Stripped; storage/eMMC/SSD control service (`/dev/copro_comms_app4`) |
| `/lib/modules/6.1.5-xilinx-v2023.1/extra/copro-comms.ko` | `ELF64` LSB `ET_REL` | `AArch64` | — | **Unstripped**; RPU<->APU IPI character driver (`/dev/copro_comms_*`) |
| `/lib/modules/6.1.5-xilinx-v2023.1/extra/copro-buf-exporter.ko` | `ELF64` LSB `ET_REL` | `AArch64` | — | **Unstripped**; CoPro physical memory -> `dma_buf` exporter |
| `/lib/modules/6.1.5-xilinx-v2023.1/extra/custom-cma.ko` | `ELF64` LSB `ET_REL` | `AArch64` | — | **Unstripped**; `custom_cma` region query/resize character driver |
| `/lib/modules/6.1.5-xilinx-v2023.1/extra/pl-sysreg.ko` | `ELF64` LSB `ET_REL` | `AArch64` | — | **Unstripped**; `atomos,pl-sysreg` UIO register/IRQ driver |
| `/lib/modules/6.1.5-xilinx-v2023.1/extra/al5e/al5e.ko` | `ELF64` LSB `ET_REL` | `AArch64` | — | **Unstripped**; Xilinx VCU / Allegro H.264/H.265 encoder (`/dev/allegroIP`) |
| `/lib/modules/6.1.5-xilinx-v2023.1/extra/dmaproxy/dmaproxy.ko` | `ELF64` LSB `ET_REL` | `AArch64` | — | **Unstripped**; Xilinx ZynqMP DMA proxy (`/dev/dmaproxy`) |

---

## 3. Target Device Nodes & `open()` Initialization Trace

### 3.1 Absence of Standard Linux V4L2 / Media Controller Video Nodes
Static string and relocation checks establish that AtomOS `video_pipeline` does **not** use standard V4L2 capture interfaces:
- **Absent in `/usr/bin/video_pipeline` and extracted rootfs daemons:** `/dev/video*`, `/dev/media*`, and V4L2 `VIDIOC_*` opcodes (`VIDIOC_REQBUFS`, `VIDIOC_QBUF`, `VIDIOC_DQBUF`).
- **UIO status (`/dev/uio*`):** Kernel modules include [`pl-sysreg.ko`](../../firmware/extracted/rootfs_ext4/lib/modules/6.1.5-xilinx-v2023.1/extra/pl-sysreg.ko) (`compatible = "atomos,pl-sysreg"` via `uio_sysreg_probe`), `uio_dmem_genirq.ko`, and `uio_pdrv_genirq.ko`. However, **no** `atomos,pl-sysreg` node appears in [`reverse-engineering/device-tree/system.dts`](../../reverse-engineering/device-tree/system.dts), and **no** extracted `/usr/bin/*` daemon opens `/dev/uio*`. Instead, PL hardware capture/raw DMA is driven by the bare-metal R5 co-processor (or FPGA DMA engine) and signaled to Linux over ZynqMP IPI mailboxes via `copro-comms.ko`.

### 3.2 Verified Device Paths & `open()` Call Sites

| Device Node / Path | Source Binary & Virtual Address | Call Context / Open Flags | Driver / Subsystem |
|---|---|---|---|
| `/dev/copro_comms_data` | `video_pipeline`: `.rodata` `0x224618` -> XREF `0x2b2d0` -> `0x2b8f4` -> `open@plt` (`0x28020`) at **`0x213284`** (in `0x213230`) | `w1 = 0x80002` (`O_RDWR \| O_CLOEXEC`); stored at `[x19, #24]` | `copro-comms.ko` (`ipi_data_ch`, `system.dts` L1668) |
| `/dev/copro_comms_ctrl` | `core_control`: `.rodata` `0x81890` | Opens channel and runs same CoPro `ioctl` client library | `copro-comms.ko` (`ipi_cntrl_ch`, `system.dts` L1675) |
| `/dev/copro_comms_app4` | `media_control`: `.rodata` `0x28f18` | Opens channel and runs same CoPro `ioctl` client library | `copro-comms.ko` (`ipi_app4_ch`, `system.dts` L1696) |
| `/dev/dma_heap` (`codec_output`) | `video_pipeline`: `.rodata` `0x24a618` -> `0x4a7e8` initializes `std::filesystem::path` at `0x2bf950`; resolved in **`0x21b660`** (checks `std::filesystem::status == 5` character device) <- **`0xa6c0c`** -> **`0xa6cb0`** `gst_dmaheap_allocator_obtain@plt` + `g_object_set(..., "heap-id", path)` (`0x2296e0` `'heap-id'`, `'codec_output'`); `libgstallocators-1.0.so.0`: `open64@plt` at **`0x3a50`** | `libgstallocators` opens `/dev/dma_heap/<name>` with `w1 = 0x2` (`O_RDWR`) | Linux `dma_heap` backed by `codec_output` CMA pool |
| `/dev/mem` | `video_pipeline`: `.rodata` `0x24af60` -> **`0x220390`** -> `open@plt` at **`0x220398`** (inside `0x220320`, called from `0x21b4f0`) | `w1 = w20 \| 0x80000` (`O_CLOEXEC`, asserts `w20 <= 2`) | Kernel `/dev/mem` physical window mapping |
| `/proc/device-tree` properties | `video_pipeline`: `open@plt` at `0x21a0b8`, `0x21a408`, `0x21b048` | `w1 = 0x80000` (`O_CLOEXEC`) + `pread@plt` | Device-tree reserved/memory lookup (`device_tree.cpp`) |
| `/dev/allegroIP`, `/dev/allegroDecodeIP`, `/dev/dmaproxy` | `/etc/udev/rules.d/99-vcu-enc-dec.rules` (L2–L6), `ctrlsw_encoder` / GStreamer OMX (`libOMX.allegro.video_encoder.so`, `liballegro_encode.so`) | `MODE="0660", GROUP="video"` | `al5e.ko`, `al5d.ko`, `dmaproxy.ko` |
| `/var/run/user/1000/atomos/video_pipeline_socket` | `video_pipeline` + [`recording-engine/vraw_daemon.c`](../../recording-engine/vraw_daemon.c) | `AF_UNIX`, `SOCK_SEQPACKET`, Protobuf `Service.Requests` | Userspace control/status IPC |

---

## 4. `ioctl()` Opcode Enumeration & Verified C Struct Layouts

### 4.1 Complete `video_pipeline` `ioctl@plt` (`0x0295a0`) Inventory (21 Call Sites)
Every `bl 0x295a0 <ioctl@plt>` instruction in `/usr/bin/video_pipeline` maps to one of five request codes (`W1`/`X1`):

| Call-Site VA(s) | Count | Register `X1`/`W1` | Decoded Symbolic Command | Target FD / Purpose |
|---|---:|---|---|---|
| `0x212de8`, `0x21361c`, `0x213640` | 3 | `0x80242000` | `_IOR(0x20, 0x00, 36)` (`COPRO_IOC_GET_MESSAGE`) | Pop next 36-byte RX message from `/dev/copro_comms_data`; auto-exports `dma_buf` FD if `(flags & 0xC0) == 0x40` |
| `0x213044` (in `0x212fe0`) | 1 | `0xc0242002` | `_IOWR(0x20, 0x02, 36)` (`COPRO_IOC_PREPARE_DMABUF`) | Attach & DMA-map `dma_fd`, writing `sg_dma_address` & `sg_dma_len` into struct offsets `+0x08` & `+0x0c` for R5 |
| `0x21383c` (in `0x2137f0`) | 1 | `0x40242001` | `_IOW(0x20, 0x01, 36)` (`COPRO_IOC_SEND_MESSAGE`) | Send 32-byte IPI payload (struct bytes `[+0x04..+0x23]`) to R5 mailbox (`dma_fd = -1`) |
| `0x1cd468` | 1 | `0x00008919` | `SIOCGIFBRDADDR` | Query IPv4 broadcast address on `AF_INET` socket (NDI/networking) |
| `0x15f588`, `0x15fa0c`, `0x15fae4`, `0x15fc8c`, `0x15fd20`, `0x17bb28`, `0x17cd3c`, `0x181358`, `0x1817e4`, `0x181bf0`, `0x181fc4`, `0x18be3c`, `0x18c11c`, `0x197a4c`, `0x19d7c4` | 15 | `0x00005421` | `FIONREAD` | Poll readable socket/pipe byte count (`libevent`/stream I/O) |

Note: `core_control` (`0x686f8`, `0x68954`, `0x68eec`, `0x68f10`, `0x6910c`) and `media_control` (`0x1c568`, `0x1c7c0`ish, plus block `BLKGETSIZE64` `0x80081272` at `0x11a7c` and `BLKRRPART` `0x1261` at `0x11f98`) embed the exact same `0x80242000` / `0x40242001` / `0xc0242002` CoPro wrapper routines.

### 4.2 `/dev/copro_comms_*` Kernel & Userspace 36-Byte Struct Layout (`copro-comms.ko`)
Disassembly of `copro_comms_ioctl()` (`0x1050`), `copro_comms_on_buffer_released()` (`0x0d20`), `video_pipeline` `0x212da0` / `0x212fe0` / `0x2137f0` proves the exact 36-byte (`0x24`) packed ABI:

```text
Offset   Size  Field        Verified Kernel & Userspace Access Evidence
------   ----  -----------  ---------------------------------------------------------------------
+0x00     4    dma_fd       int32_t; RX (0x146c: stur w0, [x28, #-40]): fd from copro_buf_exporter_get_fd()
                            TX (0x21381c): set to -1 (0xffffffff). PREPARE (0x1170): must be >= 0
+0x04     1    flags        uint8_t; IPI byte 0 (0x13e0: ldrb w2, [x23, #4]; 0x212df8: ldrb w1, [sp, #84])
                            (flags & 0xC0) == 0x40 -> buffer descriptor present (imports/attaches dma_buf)
                            Release callback (0x0d88..0x0d8c): sets byte 0 = 0xC0 before IPI TX back to R5
+0x05     1    reserved0    uint8_t; IPI byte 1 (zeroed on PREPARE/SEND in video_pipeline)
+0x06     2    msg_type     uint16_t; (0x212e04: ldrh w2, [sp, #86]; 0x213824: strh w2, [sp, #86])
+0x08     4    phys_addr    uint32_t; RX (0x13ec: ldp w4, w8, [x28, #-32] -> w4 passed to import_buffer)
                            PREPARE (0x11c0..11c4): sg_dma_address ([sg, #16]) written as w2 to [sp, #124]
+0x0C     4    size         uint32_t; RX (0x13ec: w8 passed to import_buffer arg2)
                            PREPARE (0x11cc..11d4): sg_dma_len ([sg, #12]) written as w3 to [sp, #128]
+0x10    20    payload[20]  Trailing 20 bytes (5 x uint32 words; video_pipeline passes +0x08..+0x23 = 7x u32)
```

- **Important lifetime & single-accessor rules (`copro-comms.ko` + `copro-buf-exporter.ko`):**
  - **Single-accessor enforcement (`copro_comms_open` at `0x100294`):** Unless the Device Tree node sets `allow-multiple-accessors = "true"`, `copro_comms_open()` rejects any second opener with `-EBUSY` (`-16`, `"multiple accessors not permitted"`). Inspection of [`reverse-engineering/device-tree/system.dts`](../../reverse-engineering/device-tree/system.dts#L1668-L1705) confirms `ipi_data_ch` (`copro_comms_data`) and all sibling IPI nodes omit `allow-multiple-accessors`.
  - **Automatic R5 buffer release (`copro_comms_on_buffer_released` at `0x100d20`):** When RX (`0x80242000`) receives `(flags & 0xC0) == 0x40`, `copro_comms_ioctl()` (`0x101050`) imports `[phys_addr, size]` via `copro_buf_exporter_import_buffer()` (`0x100420`), snapshots the 32-byte IPI message (`[+0x04..+0x23]`) via `copro_buf_exporter_set_priv()`, and exports an `O_RDWR | O_CLOEXEC` `dma_buf` FD (`dma_fd`). When **all** userspace references to that `dma_buf` file description are closed (`copro_buf_ex_dma_buf_release()`), the kernel automatically invokes `copro_comms_on_buffer_released()`, writes `flags = 0xC0`, and returns the 32-byte message over IPI (`ipi_mbox_send_message`).
  - Downstream C++ handlers in `video_pipeline` dispatch via `MessageRouter` (`0x314930` / ELF `+0x214930`), which walks a `std::map<uint16_t, std::shared_ptr<Callback>>` keyed by `uint16_t msg_type`:
    - **`ConfigHandler`** (`0x154ce0` / ELF `+0x054ce0`): registers `0x0040` (`DmabufCallbackReadWrite<msg_video_config_str>` at `0x152e20`, `263` B / `0x107`), `0x0041` (`0x153610`), `0x0050` (inline config at `0x153840`), `0x0051` (status query at `0x153760`), `0x0070` (`0x153d10`), `0x0071` (`0x1536b0`), `0x0072` (`DmabufCallbackReadWrite<msg_streaming_config_str>` at `0x152f70`, `426` B / `0x1AA`), `0x0078` (`DmabufCallbackReadWrite<msg_ndi_connect_src>` at `0x1530c0`, `24` B), `0x0017` (`0x153ab0`), and `0x001D` (`0x153980`).
    - **`DmaSrcElement`** (`0x1c0b40` / ELF `+0x0c0b40`, wraps `"appsrc"`): registers six callbacks for `msg_type` IDs `0x0001` (`0x1c3210`->`0x1c2f70`->`0x1c2e10`), `0x0042` (`0x1bf310`, onVideoFinish), `0x0052` (`0x1bf1a0`, onNewStream), `0x0053` (`0x1bf590`, segment bounds), `0x0054` (`0x1bf030`, onSegmentStop), and `0x0055` (`0x1c3440`->`0x1c3320`, pts/dts frame).

### 4.3 Secondary Driver `ioctl` Commands (DMA-Heap, Custom CMA, VCU `al5e`, `dmaproxy`)

| Device / Library | Request Code (`W1`) | Struct Size & Layout | Verified Evidence |
|---|---|---|---|
| `/dev/dma_heap/<name>` (`libgstallocators`) | `0xc0184800` (`DMA_HEAP_IOCTL_ALLOC`) | 24 B (`len`, `fd`, `fd_flags`, `heap_flags`) | `libgstallocators-1.0.so.0` at `0x3a6c..0x3a74` |
| Any `dma_buf` FD (`libgstallocators`) | `0x40086200` (`DMA_BUF_IOCTL_SYNC`) | 8 B (`uint64_t flags` — `START`/`END` \| `READ`/`WRITE`) | `libgstallocators-1.0.so.0` at `0x1d40..0x1d4c`, `0x1e7c..0x1e88` |
| `/dev/custom_cma` (`custom-cma.ko`) | `0xc0303000` (get region), `0x40303001` (resize) | 48 B (`char name[32]`, `uint64_t base`, `uint64_t size`) | `custom_cma_ioctl` (`0x954..0xbe0`, `cma_get_base`/`cma_get_size`) |
| `/dev/dmaproxy` (`dmaproxy.ko`) | `0xc0083201` | Copies 24 B from user (`dmaproxy_ioctl` at `0x100..0x200`: 2 FDs, 2 offsets, size) | `dmaproxy.ko` `0x1000d0+` |
| `/dev/allegroIP` (`al5e.ko`) | `0xc20c7102` (524B create), `0x7104` (destroy), `0xc4087105` (1032B encode), `0xc2047106` (516B wait), `0xc00c710d` (12B get dma fd), `0xc00c7112` (12B get dma addr), `0xc0207116` (32B put stream buf), `0xc0147117` (20B get rec), `0xc0047118` (4B release rec) | Kernel VCU command structs | `al5e_ioctl` (`0x100270..0x1007c0`) |

### 4.4 Ghidra-Decompiled CoPro Message Opcodes & Struct Layouts

1. **Verified `/dev/copro_comms_data` Opcodes** (defined as `ATOMOS_COPRO_MSG_*` in [`atomos_copro_abi.h`](../../recording-engine/atomos_copro_abi.h#L102-L123)):
   - **Frame & stream lifecycle (RX to `DmaSrcElement`):** `0x0001` (`FRAME_V1`), `0x0055` (`FRAME_V2` with `pts`/`dts`), `0x0042` (`VIDEO_FINISH`), `0x0052` (`NEW_STREAM`), `0x0053` (`SEGMENT_START`), `0x0054` (`SEGMENT_STOP`).
   - **Configuration & status (`ConfigHandler`):** `0x0040` (`VIDEO_CONFIG` indirect DMABUF `263` B), `0x0041` (`VIDEO_CONFIG_GET`), `0x0050` (`VIDEO_CFG_INLINE`), `0x0051` (`VIDEO_STATUS` -> replies via `0x0050` with `12` B `atomos_msg_video_status` inside 4 words), `0x0070` (`STREAM_CFG_INLINE`), `0x0071` (`STREAM_CFG_GET`), `0x0072` (`STREAMING_CONFIG` indirect DMABUF `426` B), `0x0078` (`NDI_CONNECT_SRC` `24` B), `0x0017` (`NDI_CONNECT`), `0x001D` (`AUDIO_CFG`).
   - **TX telemetry / setup (`video_pipeline` -> R5):** `0x001B` (`VIDEO_TIMING`), `0x001C` (`AUDIO_FORMAT`), `0x0060`/`0x0061` (`MLSP_TX_STAT_0/1`), `0x0076`/`0x007A` (`STREAM_TALKBACK_0/1`).
2. **Trailing 20-Byte `atomos_copro_msg.payload` (`+0x10..+0x23`) Interpretations:**
   - `FRAME_V1` (`0x0001`): `debug_id` (`+0x10`), `reserved1` (`+0x14`), `frame_id_word` (`+0x18`, `frameId = w & 0x7FFF`), `reserved2` (`+0x1C`), `meta_flags`/`meta_b1`/`meta_u16` (`+0x20..+0x23`).
   - `FRAME_V2` (`0x0055`): `debug_id` (`+0x10`), `reserved1` (`+0x14`), `frame_id_word` (`+0x18`, `frameId = w & 0x7FFF`), `pts` (`+0x1C`), `dts` (`+0x20`).
   - Indirect DMABUF config (`0x0040`, `0x0072`, `0x0078` via `DmabufCallbackReadWrite`): `debug_id` (`+0x10`), `reserved1` (`+0x14`), `struct_offset` (`+0x18`), `struct_len` (`+0x1C`, verified `>= 263` / `>= 426` / `>= 24`).
3. **Config & Pixel-Format Structures** (`_Static_assert` verified in [`atomos_copro_abi.h`](../../recording-engine/atomos_copro_abi.h#L180-L326)):
   - `struct atomos_msg_video_config` (`263` B = `0x107`, recovered from `0x156a10` / `0x159100`): `+0x00 result`, `+0x01 direction`, `+0x02 video_mode` (`1..8`), `+0x04 interlaced`, `+0x05 width`, `+0x07 height`, `+0x09 fps_num`, `+0x0B fps_den`, `+0x0D format_flags` (`mode[2:0] | chroma[5:4] | no_input[7]`), `+0x0E colorimetry`, `+0x10..+0x17` GStreamer queue/GOP/bitrate overrides.
   - `struct atomos_msg_streaming_config` (`426` B = `0x1AA`, recovered from `0x15a3e0` / `0x15b090`): identity strings (`model`, `user_name`, `sys_version`, `device_aid`, `device_id`), `stream_proto` (`1..11`), `stream_key_or_url[128]`, `ndi_groups[128]`, and multicast IPv4 fields ending at `+0x1A6`.
   - `struct atomos_msg_video_status` (`12` B, emitted by `0x156790` on `0x0051` -> `0x0050`): `direction`, `interlaced_bit7`, `width`, `height`, `fps_num`, `fps_den`, `format_flags`, `reserved`.
   - **Packed 32-bit `pxFmt` word (`0x31c560`, `0x31c700`, `0x31c8a0`, `0x31ca90`, `0x31cc10`):** `bits[2:0]` color mode (`1=RGB, 2=ARGB, 3=YCbCr, 4=YOnly, 5=CbCrOnly, 6=Bayer`), `bits[4:3]` chroma/Bayer (`0=4:2:2/RGGB, 1=4:4:4/GRBG, 2=4:2:0/GBRG, 3=packed/BGGR`), `bits[6:5]` depth (`0=8BPP, 1=10BPP, 2=12BPP`), `bits[17:8]` `width/8`, `bits[27:18]` `height/8`, `bit[30]` `interlaced`.

---

## 5. Physical Memory Map, `mmap()` Alignment, & Frame Buffer Flow

### 5.1 Device-Tree Reserved Memory Pools ([`system.dts`](../../reverse-engineering/device-tree/system.dts))
- `misc_cma` (`L1828`): `0x1a000000`, size `0x1000000` (`16 MiB`), `shared-dma-pool; reusable; linux,cma-default;`
- `codec_input` (`L1836`, alias `atomos_reserved`): `0x1b000000`, size `0x11000000` (`272 MiB`), `no-map;` (dedicated physical CoPro/R5/FPGA shared input window; outside normal kernel page allocator)
- `codec_output` (`L1842`, alias `cma_codec`): `0x2c000000`, size `0x34000000` (`832 MiB`), `shared-dma-pool; reusable; restrict-range = <0x00 0x4f000000 0x00 0x00>;` (bound to `al5e@a0000000` and `al5d@a0020000` via `al,custom-cma = "codec_output"`, and selected by `video_pipeline` `'codec_output'` `dma_heap` string at `0x229700`).

### 5.2 Sub-Page `mmap()` Mechanics in `video_pipeline` & `copro-buf-exporter.ko`
Combining Ghidra decompilation of `copro-buf-exporter.ko` and `video_pipeline` resolves both DMA-BUF and indirect config mappings:
1. **Frame DMA-BUF sub-page slicing (`FUN_001bf870` -> `FUN_001c6dd0` + `copro_buf_exporter_import_buffer` `0x100420` + `copro_buf_ex_mmap` `0x100d40`):**
   - `copro_buf_exporter_import_buffer()` builds a 1-entry scatterlist starting at the page-aligned base `phys_addr & ~0xFFF`, sets `sg->length = len + (phys_addr & 0xFFF)`, and `copro_buf_ex_mmap()` maps pages from `vm_pgoff << 12` (`offset = 0` maps page 0) with non-cached/WC `vm_page_prot` via `remap_pfn_range()`.
   - Therefore, in `video_pipeline`, `FUN_001bf870` (`DmaSrcElement`) computes `page_delta = phys_addr & (sysconf(_SC_PAGESIZE) - 1)` and passes `(size, page_delta)` into `FUN_001c6dd0` (`gst_dmabuf_allocator_alloc(..., size + page_delta)` + `gst_buffer_copy_region(..., page_delta, size)`). Consumers mapping `msg.dma_fd` **must** map `mmap(NULL, size + page_delta, ..., dma_fd, 0)` and read pixels from `base + page_delta` (implemented in `atomos_mmap_dmabuf_frame()`).
2. **Indirect config / `/dev/mem` page-aligned offset mapping (`FUN_00313fe0` / ELF `+0x213fe0`, `0x220320`):**
   - Used for indirect DMABUF structs (`0x0040`, `0x0072`, `0x0078` at `struct_offset`) and `/dev/mem`: `aligned = (offset / pgsz) * pgsz`, `delta = offset - aligned`, `mmap(NULL, len + delta, ..., fd, aligned)`, `data = base + delta` (implemented in `atomos_mmap_aligned()`).

### 5.3 Resolved vs Open Integration Points Against [`recording-engine/vraw_daemon.c`](../../recording-engine/vraw_daemon.c)
- **Resolved in code (`atomos_copro_abi.h`, `fake_copro_interceptor.c`, `vraw_daemon.c`):**
  1. Direct CoPro ioctl channel (`--direct-copro`) and non-blocking `SOCK_SEQPACKET` + `SCM_RIGHTS` forwarder mode (`--fwd-sock`) eliminate reliance on `video_pipeline_socket`'s `GetStatus`/`ShutDown`-only Protobuf interface while keeping `dma_buf` FDs alive via kernel `SCM_RIGHTS` refcounts until both `video_pipeline` and `vraw_daemon` close them.
  2. `atomos_mmap_dmabuf_frame()` + `atomos_dmabuf_sync()` (`START`/`END` | `READ`, ignoring `-ENOTTY`/`-EINVAL`) handle sub-page `phys_addr & (pagesize - 1)` offsets and dynamic `msg.size` bounds cleanly without assuming byte `0` or hardcoded `4K` `st_size` minimums.
  3. Incoming `0x0040` (`VIDEO_CONFIG`) updates active DNG header width/height dynamically alongside `--standalone` synthetic 4K benchmarking.
- **Requires on-hardware verification:** `video_pipeline`'s GStreamer caps advertise YUV/RGB formats (`UYVY`, `UYVP`, `NV16`, `YV12`, `I420`, `NV12`, `BGRA`/`RGBA`, `nv16_10le32`) without `bayer2rgb`, and the extracted R5 RTOS image (`part01_startrek_noresources.elf_load_64cb7238.bin`) is high-entropy/packed. Capturing live `LD_PRELOAD=libfakecopro.so` logs on a physical Ninja V during RAW recording is still required to confirm whether R5 emits Bayer frames into `codec_input`.

---

## 6. Completed Integration & Verification Summary

- **[`recording-engine/atomos_copro_abi.h`](../../recording-engine/atomos_copro_abi.h):** Houses `_Static_assert`-verified C structs (`atomos_copro_msg` 36 B, `atomos_msg_video_config` 263 B, `atomos_msg_streaming_config` 426 B, `atomos_msg_video_status` 12 B, `atomos_custom_cma_region` 48 B), `ATOMOS_COPRO_MSG_*` / `ATOMOS_PXFMT_*` definitions, and helpers (`atomos_mmap_aligned`, `atomos_mmap_dmabuf_frame`, `atomos_munmap_aligned`, `atomos_dmabuf_sync`, `atomos_copro_msg_name`, `atomos_pxfmt_decode`). Compiled cleanly under `gcc -std=c11`, `aarch64-linux-gnu-gcc -std=c11`, and `aarch64-linux-gnu-g++ -std=c++17` with `-Wall -Wextra -Werror`.
- **[`reverse-engineering/video-pipeline/fake_copro_interceptor.c`](../../reverse-engineering/video-pipeline/fake_copro_interceptor.c) -> [`libfakecopro.so`](../../reverse-engineering/video-pipeline/libfakecopro.so):** Rebuilt for ELF64 AArch64 (`-O2 -Wall -Wextra -Werror`). Decodes `atomos_copro_msg_name`, `FRAME_V1`/`FRAME_V2` (`frameId`, `pts`, `dts`), and mmap-peeked `VIDEO_CONFIG`/`STREAMING_CONFIG` payloads, and optionally forwards RX (`GET_MESSAGE` `rc == 0`) 36-byte structs + `SCM_RIGHTS` `dma_fd` over `COPRO_FWD_SOCK` (`SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC`, `MSG_NOSIGNAL | MSG_DONTWAIT`). Verified on host with `COPRO_MOCK=1 COPRO_VERBOSE=1 COPRO_LOG_EAGAIN=1`.
- **[`recording-engine/vraw_daemon.c`](../../recording-engine/vraw_daemon.c):** Integrated with `atomos_copro_abi.h`, adding `--direct-copro [dev]` and `--fwd-sock <unix_path>` alongside `--standalone`. Verified via `make -C recording-engine clean all arm64 test` (`vraw_daemon_arm64` ELF64 AArch64; 24/24 standalone 4K frames, 0 drops), strict `-Werror` builds, and an end-to-end `AF_UNIX` `SOCK_SEQPACKET` + `SCM_RIGHTS` `memfd` loopback test confirming dynamic `640x480` DNG tags (`0x0040`) and byte-for-byte sub-page `page_delta` slicing (`phys_addr = 0x1b000040`, `page_delta = 64` and `0x1b200080`, `page_delta = 128`).

