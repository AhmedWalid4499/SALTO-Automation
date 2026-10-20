"""Where things are saved: <base>/<GOLD order> - <STC>/{Downloads,Screenshots}."""
import os
import re
import shutil
import time

from .browser import DOWNLOAD_DIR


def safe(name, limit=120):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name)).strip(" .")
    return (name or "file")[:limit]


def order_folder(base, order_ref, stc_id=""):
    name = safe(f"{order_ref} - {stc_id}" if stc_id else order_ref)
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    return path


def sub(folder, *parts):
    path = os.path.join(folder, *[safe(p) for p in parts])
    os.makedirs(path, exist_ok=True)
    return path


def unique(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def numbered(folder, label, ext=".png"):
    """<folder>/<label>_<n>.png with the next free n."""
    label = safe(label, 60)
    n = 1
    while os.path.exists(os.path.join(folder, f"{label}_{n}{ext}")):
        n += 1
    return os.path.join(folder, f"{label}_{n}{ext}")


def staged():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    return set(os.listdir(DOWNLOAD_DIR))


def wait_new_download(before, timeout=25):
    """Return the path of a finished file that appeared in the download dir after `before`, or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        now = set(os.listdir(DOWNLOAD_DIR))
        new = [f for f in now - before if not f.endswith((".part", ".tmp", ".crdownload"))]
        partial = [f for f in now - before if f.endswith(".part")]
        if new and not partial:
            time.sleep(0.5)
            return os.path.join(DOWNLOAD_DIR, sorted(new)[0])
        time.sleep(0.5)
    return None


def replace_into(src, folder, name):
    """Move src to folder/name, replacing an older copy (same attachment downloaded again)."""
    dest = os.path.join(folder, name)
    os.replace(src, dest)
    return dest


def move_into(src, folder, name=None):
    stem, ext = os.path.splitext(name or os.path.basename(src))
    dest = unique(os.path.join(folder, safe(stem, 60) + ext))
    shutil.move(src, dest)
    return dest
