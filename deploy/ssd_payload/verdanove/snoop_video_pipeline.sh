#!/bin/sh
# ==============================================================================
# Verdanove CoPro Runtime Snooper & Forwarder Launcher (Ninja V AArch64)
#
# Non-destructive (100% RAM + SSD only; never modifies internal flash):
#   1. Stages libfakecopro.so and vraw_daemon_arm64 into /tmp/verdanove_bin.
#   2. Captures stock video_pipeline command-line flags from /proc, then stops
#      /etc/init.d/video_pipeline.sh cleanly.
#   3. Starts vraw_daemon_arm64 --fwd-sock /tmp/vraw_copro_fwd.sock (unless
#      --snoop-only is passed).
#   4. Relaunches /usr/bin/video_pipeline with LD_PRELOAD=libfakecopro.so and
#      COPRO_FWD_SOCK=/tmp/vraw_copro_fwd.sock, logging all CoPro RX/TX packets
#      to the SSD under verdanove/logs/.
#   5. On Ctrl+C / SIGTERM, restores stock /etc/init.d/video_pipeline.sh.
# ==============================================================================

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SRC_BIN="${SCRIPT_DIR}/bin/vraw_daemon_arm64"
SRC_LIB="${SCRIPT_DIR}/bin/libfakecopro.so"
RAM_BIN_DIR="/tmp/verdanove_bin"
BIN="${RAM_BIN_DIR}/vraw_daemon_arm64"
LIB="${RAM_BIN_DIR}/libfakecopro.so"
FWD_SOCK="/tmp/vraw_copro_fwd.sock"

LOG_DIR="${SCRIPT_DIR}/logs"
CLIPS_BASE="${SCRIPT_DIR}/clips"

SNOOP_ONLY=0
FRAMES=0
VERBOSE="${COPRO_VERBOSE:-1}"

while [ $# -gt 0 ]; do
    case "$1" in
        --snoop-only)
            SNOOP_ONLY=1
            shift
            ;;
        --frames)
            FRAMES="$2"
            shift 2
            ;;
        --quiet)
            VERBOSE=0
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--snoop-only] [--frames N] [--quiet]"
            echo "  --snoop-only  Run LD_PRELOAD=libfakecopro.so without launching vraw_daemon"
            echo "  --frames N    Stop vraw_daemon after N frames (0 = continuous)"
            echo "  --quiet       Disable COPRO_VERBOSE=1 36-byte raw hex dumps"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

mkdir -p "$RAM_BIN_DIR" "$LOG_DIR" "$CLIPS_BASE"

if [ ! -f "$SRC_LIB" ]; then
    echo "[SNOOP_ERR] Missing shared library: $SRC_LIB" >&2
    exit 1
fi
cp -f "$SRC_LIB" "$LIB"
chmod 755 "$LIB"

if [ "$SNOOP_ONLY" -eq 0 ]; then
    if [ ! -f "$SRC_BIN" ]; then
        echo "[SNOOP_ERR] Missing binary: $SRC_BIN" >&2
        exit 1
    fi
    cp -f "$SRC_BIN" "$BIN"
    chmod 755 "$BIN"
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S" 2>/dev/null || echo "session_$(date +%s)")
CLIP_DIR="${CLIPS_BASE}/CLIP_${TIMESTAMP}"
SNOOP_LOG="${LOG_DIR}/copro_snoop_${TIMESTAMP}.log"
VRAW_LOG="${LOG_DIR}/vraw_fwd_${TIMESTAMP}.log"

# Capture running /usr/bin/video_pipeline arguments (skipping argv[0])
VP_ARGS=""
VP_RUNNING_PID=$(pidof video_pipeline 2>/dev/null || true)
if [ -n "$VP_RUNNING_PID" ]; then
    FIRST_PID=$(echo "$VP_RUNNING_PID" | awk '{print $1}')
    if [ -r "/proc/${FIRST_PID}/cmdline" ]; then
        VP_ARGS=$(tr '\0' '\n' < "/proc/${FIRST_PID}/cmdline" | tail -n +2 | tr '\n' ' ')
    fi
fi
if [ -z "$VP_ARGS" ]; then
    VP_ARGS="--debug --syslog"
fi

VP_PID=""
DAEMON_PID=""
CLEANED=0

cleanup() {
    [ "$CLEANED" -eq 1 ] && return
    CLEANED=1
    echo ""
    echo "[VRAW_SNOOP] Shutting down snooped pipeline..."
    if [ -n "$VP_PID" ] && kill -0 "$VP_PID" 2>/dev/null; then
        kill -INT "$VP_PID" 2>/dev/null || true
        sleep 1
        kill -TERM "$VP_PID" 2>/dev/null || true
        wait "$VP_PID" 2>/dev/null || true
    fi
    if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        kill -INT "$DAEMON_PID" 2>/dev/null || true
        wait "$DAEMON_PID" 2>/dev/null || true
    fi
    rm -f "$FWD_SOCK"
    if [ -x /etc/init.d/video_pipeline.sh ]; then
        echo "[VRAW_SNOOP] Restoring stock video_pipeline service..."
        /etc/init.d/video_pipeline.sh start || true
    fi
    echo "[VRAW_SNOOP] Done. Snoop log saved: $SNOOP_LOG"
}
trap cleanup EXIT INT TERM

echo "[VRAW_SNOOP] Stopping stock video_pipeline..."
if [ -x /etc/init.d/video_pipeline.sh ]; then
    /etc/init.d/video_pipeline.sh stop || true
fi
for _i in 1 2 3 4 5; do
    pidof video_pipeline >/dev/null 2>&1 || break
    sleep 1
done

rm -f "$FWD_SOCK"

if [ "$SNOOP_ONLY" -eq 0 ]; then
    mkdir -p "$CLIP_DIR"
    echo "[VRAW_SNOOP] Starting vraw_daemon --fwd-sock $FWD_SOCK ($FRAMES frames -> $CLIP_DIR)..."
    "$BIN" --fwd-sock "$FWD_SOCK" "$FRAMES" "$CLIP_DIR" > "$VRAW_LOG" 2>&1 &
    DAEMON_PID=$!
    for _i in 1 2 3 4 5 6 7 8 9 10; do
        [ -S "$FWD_SOCK" ] && break
        sleep 0.2
    done
    if [ ! -S "$FWD_SOCK" ]; then
        echo "[SNOOP_ERR] Forwarder socket did not appear at $FWD_SOCK (see $VRAW_LOG)" >&2
        exit 1
    fi
fi

echo "[VRAW_SNOOP] Launching /usr/bin/video_pipeline with LD_PRELOAD=$LIB"
echo "[VRAW_SNOOP] Args: $VP_ARGS"
echo "[VRAW_SNOOP] Snoop log: $SNOOP_LOG"
echo "[VRAW_SNOOP] Press Ctrl+C to stop and restore stock video_pipeline."

ulimit -n 10000 2>/dev/null || true

if [ "$SNOOP_ONLY" -eq 0 ]; then
    LD_PRELOAD="$LIB" \
    COPRO_FWD_SOCK="$FWD_SOCK" \
    COPRO_VERBOSE="$VERBOSE" \
    GST_DEBUG_NO_COLOR=1 \
        /usr/bin/video_pipeline $VP_ARGS > "$SNOOP_LOG" 2>&1 &
else
    LD_PRELOAD="$LIB" \
    COPRO_VERBOSE="$VERBOSE" \
    GST_DEBUG_NO_COLOR=1 \
        /usr/bin/video_pipeline $VP_ARGS > "$SNOOP_LOG" 2>&1 &
fi
VP_PID=$!

wait "$VP_PID" || true

