# Tool Installation Guide (Windows 11 + WSL2 Ubuntu)

Your workstation already has **Python 3.13.5**, **Git 2.53.0**, **VS Code 1.132.0**, **Microsoft OpenJDK 21.0.11** (required for Ghidra), **NVIDIA Driver 610.62**, and **WSL2 (Ubuntu)** installed.

Below is the step-by-step installation guide for the remaining tools required for **Phase 1 (Firmware Reverse Engineering)** and **Phase 4 (Blue Compressor & ARM64 Port)**.

---

## 1. Windows Host Tools (via `winget`)

Run the following in an elevated or standard **PowerShell** terminal:

### A. 7-Zip
```powershell
winget install --id 7zip.7zip --exact --source winget
```

### B. Rust Toolchain (`rustup`, `rustc`, `cargo`)
> **Note:** For native Windows builds, `rustup` requires the Visual Studio C++ Build Tools, or you can install Rust directly inside **WSL2 Ubuntu** (recommended for cross-compiling to Linux `aarch64-unknown-linux-gnu`).
```powershell
winget install --id Rustlang.Rustup --exact --source winget
```

### C. Ghidra (Reverse Engineering Suite)
Your machine already has **Microsoft OpenJDK 21 (`C:\Program Files\Microsoft\jdk-21.0.11.10-hotspot\bin\java.exe`)**, which meets Ghidra's JDK 21+ requirement.
1. Download the official release archive from [https://github.com/NationalSecurityAgency/ghidra/releases](https://github.com/NationalSecurityAgency/ghidra/releases).
2. Verify the SHA-256 checksum published on the GitHub release page:
   ```powershell
   Get-FileHash -Algorithm SHA256 .\ghidra_*.zip
   ```
3. Extract to `C:\Tools\ghidra\` and launch via `ghidraRun.bat`.

---

## 2. WSL2 Ubuntu Tools (Recommended for Linux Firmware & ARM64 Cross-Compilation)

Because AtomOS is an embedded PetaLinux (AArch64) system, analyzing Linux filesystems, Device Trees, U-Boot images, and cross-compiling Rust/C++ for `aarch64-unknown-linux-gnu` is cleanest inside your existing **WSL2 Ubuntu** instance.

Run inside WSL2 (`wsl`):

### A. Firmware Extraction & Binary Analysis Suite
```bash
sudo apt update
sudo apt install -y \
  binwalk \
  device-tree-compiler \
  u-boot-tools \
  mtd-utils \
  squashfs-tools \
  cpio \
  p7zip-full \
  radare2 \
  file \
  binutils-aarch64-linux-gnu \
  gcc-aarch64-linux-gnu \
  g++-aarch64-linux-gnu \
  qemu-user-static
```

### B. Rust Toolchain & AArch64 Target in WSL2
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
rustup target add aarch64-unknown-linux-gnu
```

---

## 3. Post-Installation Verification Checklist

Run these commands to confirm all tools are operational before starting Phase 1:

```powershell
# Windows Host checks
7z
rustc --version
cargo --version

# WSL2 checks
wsl -e bash -c "binwalk --help | head -n 5; dtc --version; aarch64-linux-gnu-gcc --version; aarch64-linux-gnu-readelf --version; r2 -v"
```
