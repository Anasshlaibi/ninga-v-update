#!/bin/sh
### BEGIN INIT INFO
# Provides:          vraw_sidecar
# Required-Start:    video_pipeline media_control
# Default-Start:     5
# Short-Description: Verdanove RAW CinemaDNG background sidecar
### END INIT INFO

case "$1" in
  start)
    echo "Starting Verdanove RAW sidecar..."
    /usr/bin/vraw_daemon --daemon --output /run/media/NINJAV-sda1/verdanove/clips &
    ;;
  stop)
    killall vraw_daemon || true
    ;;
  *)
    echo "Usage: $0 {start|stop}"
    exit 1
    ;;
esac
exit 0

