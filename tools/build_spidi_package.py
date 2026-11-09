import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repack_fw import repack_fw

sec3_padded = '/tmp/sec3_padded.bin'
with open('/tmp/sec3_spidi.bin', 'rb') as f:
    data = f.read()

target_len = 294387712
padding_needed = target_len - len(data)
padded = data + b'\x00' * padding_needed

with open(sec3_padded, 'wb') as f:
    f.write(padded)

print(f"Written padded Section 3 payload: {len(padded)} bytes")

# Build custom firmware package
out_fw = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab/deploy/ATOMNJV_SPIDI.FW'
print(f"Packaging {out_fw}...")
repack_fw(out_fw, sec3_payload_path=sec3_padded)

print("Verification of file size:")
fw_size = os.path.getsize(out_fw)
print(f"Firmware size: {fw_size} bytes (matches 319558064: {fw_size == 319558064})")
assert fw_size == 319558064, "Size mismatch!"
print("Custom Ninja V [SPIDI] firmware package built successfully!")

