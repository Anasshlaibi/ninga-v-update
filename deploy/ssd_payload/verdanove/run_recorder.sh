#!/bin/sh
# ==============================================================================
# Verdanove RAW Recorder Execution Script (Ninja V AArch64)
#
# Safely stages binaries to /tmp/verdanove_bin (RAM tmpfs) before execution so
# exFAT mount options (e.g., noexec) never block execution or LD_PRELOAD.
# ==============================================================================

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONF_FILE="${SCRIPT_DIR}/config/vraw.conf"

if [ -f "$CONF_FILE" ]; then
    . "$CONF_FILE"
fi

SRC_BIN="${SCRIPT_DIR}/bin/vraw_daemon_arm64"
RAM_BIN_DIR="/tmp/verdanove_bin"
BIN="${RAM_BIN_DIR}/vraw_daemon_arm64"
LOG_DIR="${SCRIPT_DIR}/logs"
CLIPS_BASE="${SCRIPT_DIR}/clips"

mkdir -p "$RAM_BIN_DIR" "$LOG_DIR" "$CLIPS_BASE"

if [ ! -f "$SRC_BIN" ]; then
    echo "[VRAW_ERR] Missing binary: $SRC_BIN" >&2
    exit 1
fi

cp -f "$SRC_BIN" "$BIN"
chmod 755 "$BIN"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S" 2>/dev/null || echo "session_$(date +%s)")
CLIP_DIR="${CLIPS_BASE}/CLIP_${TIMESTAMP}"
mkdir -p "$CLIP_DIR"

LOG_FILE="${LOG_DIR}/vraw_${TIMESTAMP}.log"

echo "===================================================================="
echo " Starting Verdanove RAW Daemon..."
echo " Source Bin: $SRC_BIN"
echo " RAM Stage:  $BIN"
echo " Target Dir: $CLIP_DIR"
echo " Log File:   $LOG_FILE"
echo "===================================================================="

DAEMON_PID=""

cleanup() {
    echo ""
    echo "Stopping Verdanove RAW Daemon..."
    if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        kill -INT "$DAEMON_PID" 2>/dev/null || true
        wait "$DAEMON_PID" 2>/dev/null || true
    fi
    echo "Capture session finished cleanly."
    exit 0
}
trap cleanup INT TERM

"$BIN" "$@" "$CLIP_DIR" >> "$LOG_FILE" 2>&1 &
DAEMON_PID=$!

tail -f "$LOG_FILE" 2>/dev/null &
TAIL_PID=$!

wait "$DAEMON_PID"
RC=$?
kill "$TAIL_PID" 2>/dev/null || true
wait "$TAIL_PID" 2>/dev/null || true
exit $RC
