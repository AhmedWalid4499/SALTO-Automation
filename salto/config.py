"""User settings, stored in %APPDATA%\\SALTO Buddy\\config.json."""
import json
import os

from .version import APP_NAME

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "check_updates_on_start": True,
    "skipped_version": "",
    # each order is saved in <export_dir>/<GOLD order> - <STC>/ (Downloads, Screenshots, Excel)
    "export_dir": os.path.join(os.path.expanduser("~"), "Documents", APP_NAME),
    "subcases": True,
    "downloads": False,        # list attachments; download on demand from the Files tab
    "tab_screenshots": False,
    "show_browser": False,     # Firefox runs hidden in the background
}


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg.get("schema", 1) < 2:  # 1.4.0: attachments are chosen in the Files tab instead of all downloaded
        cfg["downloads"], cfg["schema"] = False, 2
    return cfg


def save(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
