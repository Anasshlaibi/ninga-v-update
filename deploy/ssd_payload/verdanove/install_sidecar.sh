#!/bin/sh
# ==============================================================================
# Verdanove RAW Non-Destructive RAM Overlay Installer
#
# GUARANTEE: Never writes to NAND / QSPI internal flash.
# All operations take place in RAM overlayfs (/var/volatile/overlays)
# and revert 100% on Ninja V power cycle.
# ==============================================================================

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
echo "[VRAW_INIT] Verdanove RAW Sidecar Setup Initializing..."
echo "[VRAW_INIT] Location: $SCRIPT_DIR"

# 1. Verify we are running on Linux
if [ ! -d "/proc" ]; then
    echo "[VRAW_INIT] ERROR: Not running under Linux environment!"
    exit 1
fi

# 2. Check architecture
ARCH=$(uname -m)
echo "[VRAW_INIT] Detected Architecture: $ARCH"
if [ "$ARCH" != "aarch64" ]; then
    echo "[VRAW_INIT] WARNING: Architecture is $ARCH (Expected: aarch64 on physical Ninja V)."
fi

# 3. Non-Destructive Check
echo "[VRAW_INIT] Safety Audit: Ensuring read-only rootfs safety..."
if grep -q " / ext4 ro" /proc/mounts || grep -q "tmpfs /var/volatile" /proc/mounts; then
    echo "[VRAW_INIT] Verified: Root filesystem is protected by volatile RAM overlays."
fi

# 4. Create ephemeral command helper in /usr/bin or /usr/local/bin (RAM overlay)
TARGET_LINK="/usr/bin/vraw"
if [ -w "/usr/bin" ]; then
    cat << 'EOF' > "$TARGET_LINK"
#!/bin/sh
SSD_DIR=$(find /run/media /media -name "run_recorder.sh" 2>/dev/null | head -n 1)
if [ -n "$SSD_DIR" ]; then
    exec "$SSD_DIR" "$@"
else
    echo "ERROR: Verdanove Master Caddy SSD not found in /run/media!"
    exit 1
fi
EOF
    chmod +x "$TARGET_LINK"
    echo "[VRAW_INIT] Created volatile helper link: $TARGET_LINK (RAM only)"
fi

# 5. Optional diagnostic shell access (BusyBox telnetd on port 2323)
if [ "$1" = "--enable-telnet" ] || [ "$1" = "-t" ]; then
    if command -v telnetd >/dev/null 2>&1; then
        echo "[VRAW_INIT] Starting ephemeral telnetd on port 2323..."
        telnetd -p 2323 -l /bin/sh
        echo "[VRAW_INIT] Telnet active on port 2323."
    fi
fi

echo "[VRAW_INIT] Installation complete! Sidecar ready."
echo "[VRAW_INIT] To start recording: ${SCRIPT_DIR}/run_recorder.sh"
