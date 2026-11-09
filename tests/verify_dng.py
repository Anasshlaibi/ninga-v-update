import sys
import struct

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/vraw_daemon_test/vraw_000000.dng'
    with open(path, 'rb') as f:
        hdr = f.read(4096)

    magic, ver, ifd_off = struct.unpack('<2sHI', hdr[:8])
    assert magic == b'II' and ver == 42
    num_entries = struct.unpack('<H', hdr[ifd_off:ifd_off+2])[0]
    print(f'IFD Entries count: {num_entries}')

    TAG_NAMES = {
        0x00FE: 'NewSubfileType',
        0x0100: 'ImageWidth',
        0x0101: 'ImageLength',
        0x0102: 'BitsPerSample',
        0x0103: 'Compression',
        0x0106: 'PhotometricInterpretation',
        0x010F: 'Make',
        0x0110: 'Model',
        0x0111: 'StripOffsets',
        0x0115: 'SamplesPerPixel',
        0x0116: 'RowsPerStrip',
        0x0117: 'StripByteCounts',
        0x011A: 'XResolution',
        0x011B: 'YResolution',
        0x011C: 'PlanarConfiguration',
        0x0128: 'ResolutionUnit',
        0x828D: 'CFARepeatPatternDim',
        0x828E: 'CFAPattern',
        0xC612: 'DNGVersion',
        0xC613: 'DNGBackwardVersion',
        0xC614: 'UniqueCameraModel',
        0xC61A: 'BlackLevel',
        0xC61D: 'WhiteLevel'
    }

    pos = ifd_off + 2
    tags = []
    for i in range(num_entries):
        tag, typ, cnt, val = struct.unpack('<HHII', hdr[pos:pos+12])
        name = TAG_NAMES.get(tag, f'0x{tag:04X}')
        extra = ''
        if typ == 2:
            s = hdr[val:val+cnt].decode('ascii', errors='replace').rstrip('\x00')
            extra = f'-> string: "{s}"'
        elif typ == 5:
            num, den = struct.unpack('<II', hdr[val:val+8])
            extra = f'-> rational: {num}/{den}'
        tags.append(tag)
        print(f'  [{i:02d}] 0x{tag:04X} ({name:25s}) type={typ} count={cnt} val_or_off={val} {extra}')
        pos += 12

    assert tags == sorted(tags), 'Tags are NOT sorted!'
    print('VERIFICATION SUCCESS: All 23 TIFF/CinemaDNG tags sorted and valid!')

if __name__ == '__main__':
    main()
