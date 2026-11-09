#!/usr/bin/env python3
"""
Verdanove Ninja Lab — Interactive Simulator Web Bridge
Connects the browser AtomOS 11 Touchscreen UI directly to the native vraw_daemon C recording engine.
"""

import os
import sys
import json
import time
import signal
import subprocess
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = Path(__file__).resolve().parent
STATIC_HTML = BASE_DIR / "simulator.html"
DAEMON_BIN = BASE_DIR / "recording-engine" / "vraw_daemon"
CLIPS_BASE_DIR = Path("/var/tmp/vraw_web_capture")

# Global Recording State
state = {
    "is_recording": False,
    "start_time": 0.0,
    "frames_captured": 0,
    "dropped_frames": 0,
    "throughput_mbps": 0.0,
    "timecode": "00:00:00:00",
    "clip_dir": str(CLIPS_BASE_DIR),
    "daemon_process": None,
    "log_lines": []
}

lock = threading.Lock()

def monitor_output_dir(proc, clip_dir):
    """Monitors generated frames in the background while recording."""
    last_count = 0
    t0 = time.time()
    
    while True:
        with lock:
            if not state["is_recording"] or proc.poll() is not None:
                break
        
        try:
            dngs = list(clip_dir.glob("*.dng"))
            count = len(dngs)
            elapsed = max(time.time() - t0, 0.001)
            
            # 11.87 MB per frame
            total_mb = count * 11.8656
            mb_s = total_mb / elapsed if elapsed > 0 else 0.0
            
            # 24 fps timecode
            total_frames = count
            ff = total_frames % 24
            ss = (total_frames // 24) % 60
            mm = (total_frames // 1440) % 60
            hh = (total_frames // 86400)
            tc_str = f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"
            
            with lock:
                state["frames_captured"] = count
                state["throughput_mbps"] = round(mb_s, 1)
                state["timecode"] = tc_str
        except Exception:
            pass
        
        time.sleep(0.1)

class SimulatorHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Serve simulator.html as default
        if path == "/" or path == "/index.html":
            return str(STATIC_HTML)
        return super().translate_path(path)

    def do_GET(self):
        if self.path == "/api/record/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            with lock:
                res = {
                    "is_recording": state["is_recording"],
                    "frames_captured": state["frames_captured"],
                    "dropped_frames": state["dropped_frames"],
                    "throughput_mbps": state["throughput_mbps"],
                    "timecode": state["timecode"],
                    "clip_dir": state["clip_dir"]
                }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
            
        elif self.path == "/api/clips":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            clips = []
            if CLIPS_BASE_DIR.exists():
                for item in sorted(CLIPS_BASE_DIR.iterdir()):
                    if item.is_dir():
                        dng_count = len(list(item.glob("*.dng")))
                        clips.append({
                            "name": item.name,
                            "frames": dng_count,
                            "path": str(item)
                        })
            self.wfile.write(json.dumps({"clips": clips}).encode("utf-8"))
            return

        super().do_GET()

    def do_POST(self):
        if self.path == "/api/record/start":
            with lock:
                if state["is_recording"]:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Already recording"}')
                    return
                
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                clip_dir = CLIPS_BASE_DIR / f"CLIP_{timestamp}"
                clip_dir.mkdir(parents=True, exist_ok=True)
                
                # Start daemon in continuous standalone mode (0 = continuous)
                cmd = [str(DAEMON_BIN), "--standalone", "0", str(clip_dir)]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                state["is_recording"] = True
                state["start_time"] = time.time()
                state["frames_captured"] = 0
                state["dropped_frames"] = 0
                state["throughput_mbps"] = 0.0
                state["timecode"] = "00:00:00:00"
                state["clip_dir"] = str(clip_dir)
                state["daemon_process"] = proc
                state["log_lines"] = []
                
                # Start background frame monitor
                mon_thread = threading.Thread(target=monitor_output_dir, args=(proc, clip_dir), daemon=True)
                mon_thread.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "clip_dir": str(clip_dir)}).encode("utf-8"))
            return

        elif self.path == "/api/record/stop":
            proc = None
            with lock:
                if not state["is_recording"]:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Not recording"}')
                    return
                
                proc = state["daemon_process"]
                state["is_recording"] = False

            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            with lock:
                res = {
                    "status": "stopped",
                    "frames_captured": state["frames_captured"],
                    "dropped_frames": state["dropped_frames"],
                    "throughput_mbps": state["throughput_mbps"],
                    "timecode": state["timecode"],
                    "clip_dir": state["clip_dir"]
                }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def main():
    port = 8080
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, SimulatorHandler)
    print(f"[SIMULATOR_BRIDGE] Serving AtomOS 11 Simulator on http://127.0.0.1:{port}")
    print(f"[SIMULATOR_BRIDGE] Native Daemon: {DAEMON_BIN}")
    print(f"[SIMULATOR_BRIDGE] Clips Base: {CLIPS_BASE_DIR}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[SIMULATOR_BRIDGE] Shutting down.")
        httpd.server_close()

if __name__ == "__main__":
    main()

