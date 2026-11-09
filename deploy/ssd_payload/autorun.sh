#!/bin/sh
# ==============================================================================
# Verdanove Master Caddy SSD Auto-Entrypoint
# Triggered if automount or shell executes SSD root autorun.sh
# ==============================================================================

SSD_ROOT=$(cd "$(dirname "$0")" && pwd)
echo "[AUTORUN] Verdanove SSD Mounted at: $SSD_ROOT"

if [ -x "${SSD_ROOT}/verdanove/install_sidecar.sh" ]; then
    "${SSD_ROOT}/verdanove/install_sidecar.sh" "$@"
elif [ -f "${SSD_ROOT}/verdanove/install_sidecar.sh" ]; then
    chmod +x "${SSD_ROOT}/verdanove/install_sidecar.sh"
    "${SSD_ROOT}/verdanove/install_sidecar.sh" "$@"
fi
