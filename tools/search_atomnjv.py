import os
import re

root = 'firmware'
matches = []

for dirpath, _, filenames in os.walk(root):
    for fn in filenames:
        fp = os.path.join(dirpath, fn)
        if fn.endswith(('.img', '.BIN', '.bin', '.elf', '.UB', '.so')):
            try:
                with open(fp, 'rb') as f:
                    content = f.read()
                    if b'ATOMNJV' in content:
                        print(f"Found 'ATOMNJV' in: {fp}")
                    if b'atomnjv' in content.lower():
                        pos = content.lower().find(b'atomnjv')
                        print(f"Found 'atomnjv' in: {fp} at offset 0x{pos:x} -> {content[pos:pos+30]}")
            except Exception as e:
                pass

