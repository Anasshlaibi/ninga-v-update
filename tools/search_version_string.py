import os

def search_version():
    root = 'firmware/extracted'
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(('.txt', '.BIN', '.bin', '.img', '.json', '.sh', '.UB')):
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, 'rb') as f:
                        data = f.read()
                        if b'11.19.0' in data or b'11.19' in data:
                            print(f"Found '11.19' in: {fp}")
                except Exception:
                    pass

search_version()

