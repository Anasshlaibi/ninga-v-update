#!/usr/bin/env python3
"""
AtomOS video_pipeline IPC Client & DMA-BUF Interceptor Test
Target: /var/run/user/1000/atomos/video_pipeline_socket (SOCK_SEQPACKET)

Negotiates the Google Protobuf handshake (service.proto) and captures
incoming dma_buf file descriptors passed via Unix domain socket SCM_RIGHTS.
"""

import os
import sys
import socket
import struct
import array
import mmap
import time

# Ensure tests/ is in path for service_pb2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service_pb2

def inspect_dmabuf(fd: int):
    """Inspect and validate an intercepted DMA-BUF file descriptor."""
    try:
        stat_info = os.fstat(fd)
        size = stat_info.st_size
        print(f"[DMA_BUF_INFO] FD {fd} | Size: {size} bytes ({size / (1024*1024):.2f} MB)", flush=True)
        if size > 0:
            with mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ) as mm:
                header_bytes = mm[:32]
                hex_dump = " ".join(f"{b:02X}" for b in header_bytes)
                print(f"[DMA_BUF_DATA] First 32 bytes: {hex_dump}", flush=True)
    except Exception as e:
        print(f"[DMA_BUF_INFO] Could not fstat/mmap FD {fd}: {e}", flush=True)

def main():
    target_socket = "/var/run/user/1000/atomos/video_pipeline_socket"
    if not os.path.exists(target_socket):
        alt = "/var/run/atomos/video_pipeline_socket"
        if os.path.exists(alt):
            target_socket = alt
        else:
            print(f"[!] Target socket {target_socket} not found. Start video_pipeline daemon first.", flush=True)
            sys.exit(1)

    print("====================================================================", flush=True)
    print(" AtomOS Video Pipeline IPC Client & DMA-BUF Interceptor Test", flush=True)
    print(f" Target Socket: {target_socket} (SOCK_SEQPACKET)", flush=True)
    print("====================================================================", flush=True)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    sock.settimeout(3.0)

    try:
        sock.connect(target_socket)
        print(f"[+] Connected successfully to {target_socket}", flush=True)
    except Exception as e:
        print(f"[-] Connection failed: {e}", flush=True)
        sys.exit(1)

    # Build GetStatus Protobuf request
    req = service_pb2.Requests()
    req.version = 1
    req.getStatus.SetInParent()
    raw_payload = req.SerializeToString()
    # Varint length-prefix
    length_prefix = bytearray()
    n = len(raw_payload)
    while n > 0x7F:
        length_prefix.append((n & 0x7F) | 0x80)
        n >>= 7
    length_prefix.append(n & 0x7F)
    framed_msg = bytes(length_prefix) + raw_payload

    print(f"\n[Step 1] Sending GetStatus Protobuf payload ({len(framed_msg)} bytes framed): {list(framed_msg)}", flush=True)

    try:
        sock.send(framed_msg)
        print("[+] Request sent successfully.", flush=True)
    except Exception as e:
        print(f"[-] Failed to send: {e}", flush=True)
        sock.close()
        sys.exit(1)

    print("\n[Step 2] Awaiting response and any SCM_RIGHTS file descriptors...", flush=True)

    fds = array.array("i")
    cmsg_space = socket.CMSG_SPACE(4 * fds.itemsize)

    try:
        data, ancdata, flags, addr = sock.recvmsg(4096, cmsg_space)
        print(f"[+] Received {len(data)} bytes response payload.", flush=True)

        received_fds = []
        for cmsg_level, cmsg_type, cmsg_data in ancdata:
            if cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS:
                num_fds = len(cmsg_data) // fds.itemsize
                received_fds = list(struct.unpack(f"{num_fds}i", cmsg_data[:num_fds * fds.itemsize]))
                print(f"[+] >>> INTERCEPTED {len(received_fds)} DMA-BUF File Descriptor(s): {received_fds}", flush=True)

        # Parse Protobuf Response
        resp = service_pb2.Responses()
        resp.ParseFromString(data)
        print(f"[+] Decoded Response Type: {resp.WhichOneof('body')}", flush=True)

        if resp.HasField("getStatus"):
            print(f"[+] Daemon Status: \"{resp.getStatus.status}\"", flush=True)
        elif resp.HasField("error"):
            print(f"[-] Daemon Error: reason={resp.error.reason}, interface={resp.error.interface}", flush=True)

        if received_fds:
            print("\n[Step 3] Analyzing Intercepted DMA-BUF buffers:", flush=True)
            for fd in received_fds:
                inspect_dmabuf(fd)
                os.close(fd)
        else:
            print("[*] No DMA-BUF file descriptors attached in initial status message.", flush=True)

    except socket.timeout:
        print("[-] Socket timed out waiting for response.", flush=True)
    except Exception as e:
        print(f"[-] Error receiving response: {e}", flush=True)
    finally:
        sock.close()
        print("[*] IPC Client connection closed.", flush=True)

if __name__ == "__main__":
    main()
