# Phase 0 & Phase 1 — Development Environment Report

**Generated:** 2026-11-09T00:40:00Z  
**Project:** Verdanove Ninja Lab  
**Workstation Hostname:** `LAPTOP-NF8A262L`

---

## 1. Host Hardware & Operating System

| Component | Verified Specification | Status |
| :--- | :--- | :--- |
| **Operating System** | Microsoft Windows 11 Famille (64-bit), Version `10.0.26300` (Build `26300`) | Verified |
| **CPU** | Intel Core i9-14900HX (24 Cores / 32 Logical Processors) | Verified |
| **Discrete GPU** | NVIDIA GeForce RTX 4060 Laptop GPU (8,188 MiB VRAM, Driver `610.62` / WDDM `32.0.16.1062`) | Verified |
| **Integrated GPU** | Intel UHD Graphics (Driver `32.0.101.5542`) | Verified |
| **System RAM** | 32 GB (`31.71 GiB` physical memory reported) | Verified |
| **Linux Subsystem** | WSL2 (`Ubuntu`, Kernel `6.6.87.2-microsoft-standard-WSL2` `x86_64`) | Verified |

---

## 2. Installed Development Tools (Windows Host)

| Tool | Status | Version | Path |
| :--- | :--- | :--- | :--- |
| **Python** | Installed | `Python 3.13.5` (Anaconda) | `C:\Users\HELIOS NEO 16\anaconda3\python.exe` |
| **Git** | Installed | `git version 2.53.0.windows.1` | `C:\Program Files\Git\cmd\git.exe` |
| **7-Zip (`7z`)** | Installed | `7-Zip 26.06 (x64)` | `C:\Program Files\7-Zip\7z.exe` |
| **Rustup** | Installed | `rustup 1.29.3 (edbc831ce 2026-11-02)` | `C:\Users\HELIOS NEO 16\.cargo\bin\rustup.exe` |
| **Rust Compiler (`rustc`)** | Installed | `rustc 1.99.1 (58cf8f9c3 2026-10-13)` | `C:\Users\HELIOS NEO 16\.cargo\bin\rustc.exe` |
| **Cargo** | Installed | `cargo 1.99.1 (5f94df478 2026-08-27)` | `C:\Users\HELIOS NEO 16\.cargo\bin\cargo.exe` |
| **VS Code** | Installed | `1.132.0` (`x64`) | `C:\Users\HELIOS NEO 16\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd` |
| **Java (JDK)** | Installed | Microsoft OpenJDK `21.0.11.10-hotspot` | `C:\Program Files\Microsoft\jdk-21.0.11.10-hotspot\bin\java.exe` |
| **NVIDIA SMI** | Installed | Driver `610.62` | `C:\Windows\system32\nvidia-smi.exe` |
| **WSL** | Installed | WSL 2 (Default: `Ubuntu`) | `C:\Windows\system32\wsl.exe` |
| **Winget** | Installed | Available | `C:\Users\HELIOS NEO 16\AppData\Local\Microsoft\WindowsApps\winget.exe` |
| **Chocolatey** | Installed | Available | `C:\ProgramData\chocolatey\bin\choco.exe` |

---

## 3. Installed Development & Reverse-Engineering Tools (WSL2 Ubuntu Environment)

| Tool | Status | Version | Path | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Binwalk** | Installed | `Binwalk v2.3.3` | `/usr/bin/binwalk` | Firmware container, entropy, and embedded payload scanning |
| **Device Tree Compiler (`dtc`)** | Installed | `DTC 1.7.0` | `/usr/bin/dtc` | Decompiling `.dtb` Flattened Device Tree blobs into `.dts` source |
| **U-Boot Tools (`mkimage`/`dumpimage`)** | Installed | `2025.10` | `/usr/bin/mkimage`, `/usr/bin/dumpimage` | Inspecting and extracting U-Boot FIT (`FLASH.UB`, `RAMDISK.UB`) and legacy images |
| **Radare2 (`r2`)** | Installed | `radare2 5.5.0` | `/usr/bin/r2` | CLI static binary disassembly, CFG analysis, and cross-reference inspection |
| **AArch64 Cross-Compiler (`gcc`/`g++`)** | Installed | `Ubuntu 13.3.0-6ubuntu2~24.04.1` | `/usr/bin/aarch64-linux-gnu-gcc` | Cross-compiling C/C++ and linking Rust `aarch64-unknown-linux-gnu` binaries |
| **Squashfs Tools (`unsquashfs`)** | Installed | `4.6.1` | `/usr/bin/unsquashfs` | Embedded filesystem inspection |
| **p7zip (`7z`)** | Installed | `23.01` | `/usr/bin/7z` | Archive and filesystem image inspection |
| **GNU Binutils (Host & AArch64)** | Installed | `2.42` | `/usr/bin/aarch64-linux-gnu-objdump`, `readelf` | ELF header, dynamic symbol, and AArch64 disassembly inspection |
| **Python 3** | Installed | `3.12.3` | `/usr/bin/python3` | Scripting & container parsing |

---

## 4. Deferred Optional GUI Tool

| Tool | Target Environment | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Ghidra** | Windows Host (OpenJDK 21 ready) | Deferred (Manual install by user when needed) | CLI analysis currently covered by `radare2 5.5.0` and `aarch64-linux-gnu-objdump` |
