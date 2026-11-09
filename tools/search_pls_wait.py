import os

root = 'firmware/extracted'
for dirpath, _, filenames in os.walk(root):
    for fn in filenames:
        fp = os.path.join(dirpath, fn)
        if fn.endswith(('.bin', '.elf', '.UB', '.img')):
            try:
                with open(fp, 'rb') as f:
                    data = f.read()
                    if b'PLS_WAIT' in data or b'pls_wait' in data or b'FWFAILED' in data:
                        print(f"Match in: {fp}")
            except Exception:
                pass

