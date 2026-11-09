#!/bin/sh
# ==============================================================================
# Verdanove RAW Recorder Execution Script (Ninja V AArch64)
# ==============================================================================

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONF_FILE="${SCRIPT_DIR}/config/vraw.conf"

if [ -f "$CONF_FILE" ]; then
    . "$CONF_FILE"
fi

BIN="${SCRIPT_DIR}/bin/vraw_daemon_arm64"
LOG_DIR="${SCRIPT_DIR}/logs"
CLIPS_BASE="${SCRIPT_DIR}/clips"

mkdir -p "$LOG_DIR"
mkdir -p "$CLIPS_BASE"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S" 2>/dev/null || echo "session_$(date +%s)")
CLIP_DIR="${CLIPS_BASE}/CLIP_${TIMESTAMP}"
mkdir -p "$CLIP_DIR"

LOG_FILE="${LOG_DIR}/vraw_${TIMESTAMP}.log"

echo "===================================================================="
echo " Starting Verdanove RAW Daemon..."
echo " Binary:     $BIN"
echo " Target Dir: $CLIP_DIR"
echo " Log File:   $LOG_FILE"
echo "===================================================================="

# Check executable permissions
if [ ! -x "$BIN" ]; then
    chmod +x "$BIN"
fi

# Trap signals for graceful shutdown
cleanup() {
    echo ""
    echo "Stopping Verdanove RAW Daemon..."
    killall -SIGINT vraw_daemon_arm64 2>/dev/null
    wait
    echo "Capture session finished cleanly."
    exit 0
}
trap cleanup INT TERM

# Run the daemon
"$BIN" "$@" "$CLIP_DIR" 2>&1 | tee -a "$LOG_FILE"
