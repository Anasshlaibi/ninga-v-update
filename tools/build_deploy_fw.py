import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repack_fw import repack_fw

deploy_path = '/mnt/c/Users/HELIOS NEO 16/Documents/framatomos/verdanove-ninja-lab/deploy/ATOMNJV.FW'
print("Building master ATOMNJV.FW container...")
repack_fw(deploy_path)
print("Finished building ATOMNJV.FW.")

