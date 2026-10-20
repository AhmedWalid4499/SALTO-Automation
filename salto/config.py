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
    "flip": True,              # FLIP serial numbers for EQP sub-cases
    "full_audit": False,       # every audit page (slow) instead of the latest one
    "show_browser": False,     # Firefox runs hidden in the background
    # Ask Buddy team key: a folder only Orange staff can open (SharePoint/Teams sync or network share) holding
    # salto-buddy-team.key. Set TEAM_KEY_DIR below to make it the built-in default for everyone.
    "team_key_dir": "",
}

TEAM_KEY_DIR = ""  # e.g. r"\\server\team\SALTO Buddy": the key itself never goes in this repo
TEAM_KEY_FILE = "salto-buddy-team.key"


def team_key_path(cfg):
    folder = cfg.get("team_key_dir") or TEAM_KEY_DIR
    return os.path.join(os.path.expandvars(folder), TEAM_KEY_FILE) if folder else ""


def portable(path):
    """Store a folder relative to %USERPROFILE%, so a SharePoint sync path works on colleagues' PCs too."""
    home = os.path.expanduser("~")
    if path.lower().startswith(home.lower() + os.sep):
        return "%USERPROFILE%" + path[len(home):]
    return path


def _sync_roots():
    """Folders OneDrive syncs on this PC: personal OneDrive (with SharePoint shortcuts) and synced SharePoint libraries."""
    roots = []
    try:
        import winreg
        base = r"Software\SyncEngines\Providers\OneDrive"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sub:
                    roots.append(winreg.QueryValueEx(sub, "MountPoint")[0])
    except OSError:
        pass
    roots.append(os.environ.get("OneDriveCommercial", ""))
    return [r for r in dict.fromkeys(roots) if r and os.path.isdir(r)]


def find_team_key(max_depth=4):
    """Look for salto-buddy-team.key in the synced folders. Returns its folder or ''."""
    for root in _sync_roots():
        base_depth = root.rstrip(os.sep).count(os.sep)
        for folder, dirs, files in os.walk(root):
            if TEAM_KEY_FILE in files:
                return folder
            if folder.count(os.sep) - base_depth >= max_depth:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if not d.startswith((".", "$"))]
    return ""


def read_team_key(cfg):
    path = team_key_path(cfg)
    try:
        with open(path, encoding="utf-8-sig") as f:  # -sig: files saved with Notepad may start with a BOM
            return f.read().strip()
    except OSError:
        return ""


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
