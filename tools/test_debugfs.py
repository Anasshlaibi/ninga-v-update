import subprocess
import os

img = '/tmp/test_ext4.img'
subprocess.run(['dd', 'if=/dev/zero', f'of={img}', 'bs=1M', 'count=2'], check=True, capture_output=True)
subprocess.run(['mkfs.ext4', '-F', img], check=True, capture_output=True)

dummy = '/tmp/hello.txt'
with open(dummy, 'w') as f:
    f.write('Hello World')

# Test debugfs write
res = subprocess.run(['debugfs', '-w', '-R', f'write {dummy} hello.txt', img], capture_output=True, text=True)
print("Write out:", res.stdout.strip(), res.stderr.strip())

# Test set mode to 0755
res = subprocess.run(['debugfs', '-w', '-R', 'set_inode_field hello.txt mode 0100755', img], capture_output=True, text=True)
print("Set mode out:", res.stdout.strip(), res.stderr.strip())

# Test symlink: symlink <link_filename> <target_string>
res = subprocess.run(['debugfs', '-w', '-R', 'symlink hello_link hello.txt', img], capture_output=True, text=True)
print("Symlink out:", res.stdout.strip(), res.stderr.strip())

# Test stat
res = subprocess.run(['debugfs', '-R', 'stat hello.txt', img], capture_output=True, text=True)
print("Stat mode lines:", [l for l in res.stdout.splitlines() if 'Mode:' in l])

os.remove(img)
os.remove(dummy)
