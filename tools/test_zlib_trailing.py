import zlib

with open('/tmp/sec3_spidi.bin', 'rb') as f:
    raw_gz = f.read()

padded = raw_gz + b'\x00' * 640136

d = zlib.decompressobj(wbits=31)
try:
    res = d.decompress(padded)
    print("Decompressed len:", len(res))
    print("Unused data len:", len(d.unused_data))
    print("EOF reached:", d.eof)
except Exception as e:
    print("Exception:", e)

