import glob

files = glob.glob('firmware/extracted/sec4_parts/*') + glob.glob('firmware/extracted/sec5_parts/*') + glob.glob('firmware/extracted/fat16_fs/*.BIN')

for fp in files:
    if fp.endswith('.img'): continue
    try:
        with open(fp, 'rb') as f:
            data = f.read()
            if b'PLS_WAIT' in data or b'pls_wait' in data or b'FWFAILED' in data:
                print(f"Match in: {fp}")
            if b'ATOMNJV' in data:
                print(f"ATOMNJV Match in: {fp}")
    except Exception as e:
        pass
print("Done.")

