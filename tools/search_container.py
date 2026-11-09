import glob

for p in glob.glob('firmware/extracted/sec4_parts/*'):
    with open(p, 'rb') as f:
        data = f.read()
        if b'wfsa' in data or b'asfw' in data:
            print('Found container magic in:', p)
        if b'\xaa\xaa\xaa\xaa' in data:
            print('Found 0xaaaaaaaa in:', p)

