#!/bin/sh
# ==============================================================================
# Verdanove SSD One-Shot Boot Hook (Executed by /etc/init.d/verdanove_hook)
#
# Runs automatically when F:\verdanove\autorun_once.sh is present on the SSD
# inside a Ninja V patched with ATOMNJV_VERDANOVE_HOOK.FW.
# 100% RAM-overlay & SSD logging only (never touches internal flash).
# ==============================================================================

set -e

SSD_DIR="${SSD_VERDANOVE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
RAM_DIR="/tmp/verdanove_bin"
FWD_SOCK="/tmp/vraw_copro_fwd.sock"
TS=$(date +"%Y%m%d_%H%M%S" 2>/dev/null || echo "boot_$(date +%s)")
CLIP_DIR="${SSD_DIR}/clips/AUTO_${TS}"
VRAW_LOG="${SSD_DIR}/logs/vraw_auto_${TS}.log"
SYSLOG_COPY="${SSD_DIR}/logs/copro_syslog_${TS}.log"

echo "[VRAW_AUTO] Starting at $(date 2>/dev/null || echo boot) from $SSD_DIR"

mkdir -p "$RAM_DIR" "${SSD_DIR}/logs" "$CLIP_DIR"
cp -f "${SSD_DIR}/bin/vraw_daemon_arm64" "${RAM_DIR}/vraw_daemon_arm64"
cp -f "${SSD_DIR}/bin/libfakecopro.so" "${RAM_DIR}/libfakecopro.so"
chmod 755 "${RAM_DIR}/vraw_daemon_arm64" "${RAM_DIR}/libfakecopro.so"

# 1. Inject LD_PRELOAD + COPRO_FWD_SOCK into RAM-overlayed /etc/default/video_pipeline
#    so both stock start and core_control mode-switch restarts keep snooping active.
if [ -w /etc/default/video_pipeline ] || [ -w /etc/default ]; then
    if ! grep -q "libfakecopro.so" /etc/default/video_pipeline 2>/dev/null; then
        {
            echo ""
            echo "# Added transiently in RAM overlay by Verdanove autorun_once.sh"
            echo "export LD_PRELOAD=${RAM_DIR}/libfakecopro.so"
            echo "export COPRO_FWD_SOCK=${FWD_SOCK}"
            echo "export COPRO_VERBOSE=1"
        } >> /etc/default/video_pipeline
        echo "[VRAW_AUTO] Injected LD_PRELOAD into RAM /etc/default/video_pipeline"
    fi
fi

# 2. Start vraw_daemon --fwd-sock in background (captures first 24 forwarded frames)
rm -f "$FWD_SOCK"
"${RAM_DIR}/vraw_daemon_arm64" --fwd-sock "$FWD_SOCK" 24 "$CLIP_DIR" > "$VRAW_LOG" 2>&1 &
for _i in 1 2 3 4 5 6 7 8 9 10; do
    [ -S "$FWD_SOCK" ] && break
    sleep 1
done

# 3. Restart stock video_pipeline via init script so it picks up LD_PRELOAD
if [ -x /etc/init.d/video_pipeline.sh ]; then
    echo "[VRAW_AUTO] Restarting video_pipeline.sh under LD_PRELOAD..."
    /etc/init.d/video_pipeline.sh stop || true
    sleep 1
    /etc/init.d/video_pipeline.sh start || true
fi

# 4. Snapshot syslog CoPro trace onto the SSD over the next 30 seconds
for _sec in 1 2 3 4 5 6; do
    sleep 5
    if [ -r /var/log/messages ]; then
        grep -E "COPRO_|DMA_HEAP|CUSTOM_CMA|video_pipeline|VRAW" /var/log/messages > "$SYSLOG_COPY" 2>/dev/null || true
    elif command -v logread >/dev/null 2>&1; then
        logread | grep -E "COPRO_|DMA_HEAP|CUSTOM_CMA|video_pipeline|VRAW" > "$SYSLOG_COPY" 2>/dev/null || true
    fi
    sync || true
done

echo "[VRAW_AUTO] Snapshot complete. Inspect logs in ${SSD_DIR}/logs/"

