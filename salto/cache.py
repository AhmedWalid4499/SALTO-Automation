"""Saved copies of orders already read, so reopening one is instant (a refresh runs behind it).

Stored per Windows user in %APPDATA%\\SALTO Buddy\\cache\\<order>.pkl, tagged with the
app version (a copy from another version is ignored).
"""
import os
import pickle
import time

from .config import CONFIG_DIR
from .files import safe
from .version import __version__

CACHE_DIR = os.path.join(CONFIG_DIR, "cache")


def _path(order_ref):
    return os.path.join(CACHE_DIR, safe(order_ref) + ".pkl")


def save(rep):
    if not rep or not rep.stc_id:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _path(rep.order_ref) + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump({"version": __version__, "saved": time.time(), "rep": rep}, f)
    os.replace(tmp, _path(rep.order_ref))


def load(order_ref):
    """(rep, saved_timestamp) or (None, None)."""
    try:
        with open(_path(order_ref), "rb") as f:
            data = pickle.load(f)
        if data.get("version") == __version__:
            return data["rep"], data["saved"]
    except Exception:  # missing, from an older version, or damaged: just read SALTO again
        pass
    return None, None
