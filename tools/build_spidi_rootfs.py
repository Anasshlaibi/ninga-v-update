import os
import subprocess
import shutil

def build_rootfs():
    base_dir = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab'
    orig_img = os.path.join(base_dir, 'firmware', 'extracted', 'rootfs_decompressed.img')
    work_img = '/tmp/rootfs_spidi.img'
    
    daemon_bin = os.path.join(base_dir, 'deploy', 'ssd_payload', 'verdanove', 'bin', 'vraw_daemon_arm64')
    init_script = os.path.join(base_dir, 'deploy', 'vraw_sidecar.sh')

    print("1. Staging files in /tmp without spaces...")
    shutil.copyfile(daemon_bin, '/tmp/vraw_daemon')
    shutil.copyfile(init_script, '/tmp/vraw_sidecar.sh')
    with open('/tmp/product_name', 'w') as f:
        f.write("Ninja V [SPIDI]\n")
    with open('/tmp/issue', 'w') as f:
        f.write("AtomOS 11.19.00 - SPIDI EDITION\n")

    print("2. Copying original rootfs...")
    shutil.copyfile(orig_img, work_img)

    cmd_script = """
cd /usr/bin
write /tmp/vraw_daemon vraw_daemon
set_inode_field vraw_daemon mode 0100755
cd /etc/init.d
write /tmp/vraw_sidecar.sh vraw_sidecar.sh
set_inode_field vraw_sidecar.sh mode 0100755
cd /etc/rc5.d
symlink S99vraw_sidecar.sh ../init.d/vraw_sidecar.sh
cd /etc
write /tmp/product_name product_name
set_inode_field product_name mode 0100644
rm issue
write /tmp/issue issue
set_inode_field issue mode 0100644
"""
    with open('/tmp/debugfs_cmds.txt', 'w') as f:
        f.write(cmd_script.strip() + "\n")

    print("3. Running debugfs commands...")
    res = subprocess.run(['debugfs', '-w', '-f', '/tmp/debugfs_cmds.txt', work_img], capture_output=True, text=True)
    if res.stderr:
        print("debugfs err:", res.stderr)

    print("4. Checking installed files...")
    res = subprocess.run(['debugfs', '-R', 'stat /usr/bin/vraw_daemon', work_img], capture_output=True, text=True)
    assert 'Inode:' in res.stdout, "vraw_daemon not found!"
    print("VERIFIED: /usr/bin/vraw_daemon installed successfully!")

    res = subprocess.run(['debugfs', '-R', 'stat /etc/product_name', work_img], capture_output=True, text=True)
    assert 'Inode:' in res.stdout, "product_name not found!"
    print("VERIFIED: /etc/product_name installed successfully!")

    res = subprocess.run(['debugfs', '-R', 'stat /etc/rc5.d/S99vraw_sidecar.sh', work_img], capture_output=True, text=True)
    assert 'Inode:' in res.stdout, "S99vraw_sidecar.sh not found!"
    print("VERIFIED: /etc/rc5.d/S99vraw_sidecar.sh installed successfully!")

    print("5. Checking filesystem integrity with fsck.ext4...")
    res = subprocess.run(['fsck.ext4', '-fn', work_img], capture_output=True, text=True)
    print("fsck summary:", res.stdout.splitlines()[-2:] if res.stdout else "OK")

    print("Rootfs modification completed successfully: /tmp/rootfs_spidi.img ready!")

if __name__ == '__main__':
    build_rootfs()
