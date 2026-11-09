# Phase 6: Hardware Execution Vectors & Firmware Rootfs Audit

**Project:** Verdanove Atomos Ninja V RAW Engine  
**Target:** Atomos Ninja V (Zynq UltraScale+ XCZU5EV / Quad Cortex-A53 @ 1.2GHz + Dual Cortex-R5 @ 500MHz)  
**Firmware Baseline:** AtomOS 11.19.00  
**Status:** Completed & Ground-Truth Verified  

---

## 1. Executive Summary

To satisfy our primary engineering commitment — **never risk bricking the Atomos Ninja V by reflashing encrypted FPGA bitstreams (`DPGA*.BIN`) or Cortex-R5 co-processor partitions (`APP0000.BIN`)** — we conducted a comprehensive forensic audit of the extracted AtomOS 11.19.00 root filesystem (`rootfs_ext4`), initramfs (`ramdisk_fs`), and U-Boot second-stage bootloader (`u-boot.elf`).

The purpose of this audit is to identify non-destructive, persistent, or semi-persistent execution vectors for the Verdanove RAW daemon (`vraw_daemon`) without altering the internal read-only flash storage.

---

## 2. Forensic Audit of Filesystem & Services

### 2.1. Udev Rules & Storage Automounting (`/etc/udev/rules.d/`)

| Rule File | Trigger Subsystem | Target Executable / Script | Description & Purpose |
|:---|:---|:---|:---|
| `automount.rules` | `SUBSYSTEM=="block"` | `/etc/udev/scripts/mount.sh` | Automatically mounts block partitions (`sda1`, `sdb1`) under `/run/media/<LABEL-name>` or `/run/media/<name>`. |
| `media_events.rules` | `SUBSYSTEM=="block"` | `/usr/lib/media_control/media_events --syslog` | Sends Protobuf event notifications (`MediaEvents.BlockMediaChange`) to AtomOS `core_control` via IPC socket. |
| `localextra.rules` | `KERNEL=="rtc0"`, `KERNEL=="fb0"`, `SUBSYSTEM=="input"` | Symlink creation & `chmod 660` | Sets up `/dev/rtc`, `/dev/fb`, and grants input group access to touchscreens and buttons. |
| `40-libgphoto2.rules` | `SUBSYSTEM=="usb"` | `/lib/udev/check-ptp-camera` | Detects connected DSLRs / mirrorless cameras over USB for camera control. |
| `72-ethernet.rules` | `SUBSYSTEM=="net"` | Name assignment | Assigns names to onboard/USB ethernet interfaces. |
| `99-vcu-enc-dec.rules`| `KERNEL=="allegro*"` | Device permissions | Sets permissions for Allegro VCU hardware encoder/decoder nodes (`/dev/allegroDecodeIP`, `/dev/allegroIP`). |

#### Automount Script Analysis (`/etc/udev/scripts/mount.sh`)
- Inspecting `mount.sh` reveals standard Yocto/OpenEmbedded automount behavior:
  - Formats supported: `ext4`, `ext3`, `vfat`, `exfat`, `ntfs`.
  - Target mount path: `/run/media/<LABEL-partition>` (e.g., `/run/media/ATOMOS-sda1`).
  - **Autorun Script Execution:** `mount.sh` does **not** contain automated calls to `autorun.sh` or `.sh` scripts located on the root of mounted media. External drives are treated purely as media storage.

---

### 2.2. Boot Configuration & Overlay Architecture (`/etc/init.d/rw-overlays.sh`)

One of the most significant discoveries in the stock AtomOS 11 rootfs is the volatile overlay mechanism:

```sh
# /etc/default/rw-overlays
DEV_MODE=true
DEV_PERSIST=
```

1. **`DEV_MODE=true` is enabled by default in production firmware!**
2. In `rw-overlays.sh`:
   - An `overlayfs` mount is established over `/etc`, `/lib/firmware/overlays`, `/home/root`, and `/lib/modules/$(uname -r)`.
   - Upper layers reside in `/var/volatile/overlays` (tmpfs in RAM).
   - Any modifications made in `/etc`, `/home/root`, or `/lib/firmware` at runtime are **strictly non-destructive and volatile**: they do not write to the underlying read-only NAND/QSPI flash and automatically revert on power-off.
3. **Application Overlay Layers (`/opt`):**
   - Stock AtomOS application packages are stored as squashfs/ext4 images in `/media/resources/APU*.BIN`.
   - `rw-overlays.sh` mounts them in numerical order (`/media/app/overlays/[0-9][0-9][0-9][0-9]`) and overlays them into `/opt` via `volatile_mount opt /opt "" "$layers" ,ro`.

---

### 2.3. Developer Debug Hooks & Service Bypasses

The startup scripts in `/etc/init.d/` explicitly provide built-in developer bypasses:

1. **Service Disabling via `.nostart`:**
   - `/etc/init.d/media_control.sh` checks for `/etc/default/media_control.nostart`. If present, it exits immediately without launching the stock media controller.
   - `/etc/init.d/video_pipeline.sh` checks for `/etc/default/video_pipeline.nostart`. If present, it exits immediately.
2. **Debug Binary Fallbacks:**
   - `video_pipeline.sh` defines:
     ```sh
     DEBUG_DAEMON=/home/root/video_pipeline
     PERF_DAEMON=/home/root/perf/video_pipeline
     ```
     When running `stop` or `status`, it actively monitors whether a custom developer binary is running under `/home/root/video_pipeline`.

---

### 2.4. Hardware Console & Diagnostic Interfaces

1. **UART Serial Console (`ttyPS0`):**
   - `/etc/inittab` line 31: `PS0:12345:respawn:/bin/start_getty 115200 ttyPS0 vt102`
   - The primary serial console on the Zynq UltraScale+ PS UART0 is active at **115200 baud, 8N1**.
   - `/etc/securetty` includes `ttyPS0`, permitting root console sessions if authentication is bypassed.
2. **Telnet & Network Daemons:**
   - `/usr/sbin/telnetd` is present on the rootfs as a BusyBox applet symlink (`/etc/busybox.links`).
   - It is not enabled by default in `/etc/init.d/` or `/etc/rc5.d/`, but can be launched instantly via any execution hook.

---

### 2.5. U-Boot Distro Boot Evaluation (`u-boot.elf`)

Disassembly and string analysis of `sec4_parts/part07_u-boot.elf_load_08000000.bin` confirms:
- Standard U-Boot distro boot targets are compiled in:
  `boot_targets=jtag mmc0 mmc1 qspi0 nand0 usb0 usb1 scsi0 pxe dhcp`
- Default script scanning checks for:
  `boot_scripts=boot.scr.uimg boot.scr`
- `scsi0` maps to the SATA SSD connector (Master Caddy).
- **Default Boot Command:** `bootcmd=go_standalone 0xc100000` (launches `phoenix_boot.bin`).

---

## 3. Comparison of Non-Destructive Execution Vectors

| Vector | Mechanism | Risk Level | Flash Touch? | Persistence | Operational Viability |
|:---|:---|:---:|:---:|:---:|:---|
| **Vector 1: SSD-Resident Sidecar via Serial/UART** | Connect via 115200 baud UART test points; run binary directly from `/run/media/sda1/vraw_daemon`. | **Zero** | No (0%) | Ephemeral | **Highest for lab development.** Completely safe; stock firmware remains pristine. |
| **Vector 2: RAM Overlay Injection (`DEV_MODE`)** | Leverage `/etc/default/rw-overlays` volatile tmpfs mounts to inject `vraw_daemon` service files into `/etc/init.d/`. | **Zero** | No (0%) | Reverts on reboot | **Safe for live testing.** System returns to 100% factory state on power cycle. |
| **Vector 3: Master Caddy U-Boot Script (`boot.scr`)** | Place `boot.scr` on Master Caddy SSD root to hook distro boot before kernel launch. | **Low** | No (0%) | Persistent on SSD | Viable if `distro_bootcmd` is reached before standalone fallback. |
| **Vector 4: Additive Firmware Layer (APU Overlay)** | Package `vraw_daemon` into an additive `APU000X.BIN` squashfs layer without touching existing `APU0000.BIN` or FPGA bitstreams. | **Low** | Yes (Additive) | Permanent | **Production release path.** Integrates seamlessly into the stock AtomOS 11 update mechanism without bricking risk. |

---

## 4. Architectural Recommendation for Verdanove RAW

1. **Development & Lab Testing Phase:**
   Run `vraw_daemon` as a **standalone sidecar binary** loaded from the SATA SSD (`/run/media/sda1/vraw_daemon`) or tested in the QEMU/WSL emulation environment. Zero flash modification.
2. **Stock System Protection:**
   Never replace or reflash `DPGA*.BIN` (FPGA bitstreams) or `APP0000.BIN` (Cortex-R5). The co-processor and FPGA maintain camera communication, HDMI/SDI ingest, and hardware watchdog timers. Modifying them risks a hard brick.
3. **User-Facing Integration:**
   `vraw_daemon` communicates exclusively over the Linux userspace UNIX domain socket `/var/run/user/1000/atomos/video_pipeline_socket` via `SOCK_SEQPACKET`, extracting frame descriptors via `SCM_RIGHTS` without altering the stock AtomOS UI or factory scopes.

