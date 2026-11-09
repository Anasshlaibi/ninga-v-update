import os

def search():
    for root, _, files in os.walk('firmware'):
        for f in files:
            if f.endswith(('.elf', '.bin', '.so', 'FLASH.UB', 'RAMDISK.UB')):
                p = os.path.join(root, f)
                try:
                    with open(p, 'rb') as fp:
                        data = fp.read()
                        if b'wfsa' in data:
                            print("Found wfsa in:", p)
                        if b'asfw' in data:
                            print("Found asfw in:", p)
                        if b'nibx' in data:
                            print("Found nibx in:", p)
                        if b'xbin' in data:
                            print("Found xbin in:", p)
                except Exception:
                    pass

search()

