import requests
import zipfile
import io
import os

BASE = r"c:\Users\steven\Documents\HW\gkp2026"

def download_zip(repo, dest):
    url = f"https://github.com/{repo}/archive/refs/heads/master.zip"
    print(f"Downloading {repo}...")
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        print(f"  Error: {r.status_code}")
        return False
    print(f"  Downloaded {len(r.content)} bytes")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(dest)
    # rename to clean name
    extracted = os.path.join(dest, os.listdir(dest)[0])
    if os.path.isdir(extracted):
        new_name = os.path.join(dest, dest.split('\\')[-1].replace('_repo', ''))
        os.rename(extracted, new_name)
    print(f"  Extracted to {new_name}")
    return True

print("=== Downloading repos ===")
os.makedirs(BASE, exist_ok=True)

# UltimateAntiCheat
ua_path = os.path.join(BASE, "UltimateAntiCheat")
if not os.path.exists(ua_path):
    download_zip("AlSch092/UltimateAntiCheat", ua_path)
else:
    print(f"  {ua_path} exists, skipping")

# VMAware
vm_path = os.path.join(BASE, "VMAware")
if not os.path.exists(vm_path):
    download_zip("NotRequiem/VMAware", vm_path)
else:
    print(f"  {vm_path} exists, skipping")

print("\n=== Done ===")
