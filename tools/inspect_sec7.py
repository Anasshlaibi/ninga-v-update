import struct

with open('firmware/original/ATOMNJV.FW', 'rb') as f:
    f.seek(0x130c10d4 + 24)
    sec7_payload = f.read(192)
    print("Sec 7 payload length:", len(sec7_payload))
    print(sec7_payload.hex())
    # Sec 7 has 192 bytes = 8 entries * 24 bytes each!
    for i in range(8):
        entry = sec7_payload[i*24:(i+1)*24]
        words = struct.unpack('<6I', entry)
        print(f"Entry {i}:", [hex(w) for w in words])

