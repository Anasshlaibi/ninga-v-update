import gzip

with open('/tmp/sec3_spidi.bin', 'rb') as f:
    data = f.read()

target_len = 294387712
padding_needed = target_len - len(data)
print(f"Padding needed: {padding_needed} bytes")

padded_data = data + b'\x00' * padding_needed
print(f"Padded length: {len(padded_data)} (matches target: {len(padded_data) == target_len})")

# Test decompressing
decomp = gzip.decompress(padded_data)
print(f"Decompressed successfully! Length: {len(decomp)} bytes")
assert len(decomp) == 355729408, "Decompressed length mismatch!"
print("100% VERIFIED: Zero-padded gzip decompresses perfectly to exact FAT16 image size!")

