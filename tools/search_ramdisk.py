import os

root = 'firmware/extracted/ramdisk_fs'
keywords = [b'ATOMNJV', b'.FW', b'asfw', b'wfsa', b'update', b'upgrade', b'firmware']

for dirpath, _, filenames in os.walk(root):
    for fn in filenames:
        fp = os.path.join(dirpath, fn)
        try:
            with open(fp, 'rb') as f:
                content = f.read()
                for kw in [b'ATOMNJV', b'.FW', b'asfw', b'wfsa']:
                    if kw in content:
                        print(f"Found {kw} in {fp}")
        except Exception:
            pass

print("Search completed.")

