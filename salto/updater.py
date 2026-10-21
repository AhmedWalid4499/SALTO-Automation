"""Updates from GitHub Releases.

Each release (made by release.ps1) is tagged vX.Y.Z and carries the
installer SALTO-Buddy-Setup-X.Y.Z.exe as an asset. On start the app asks
GitHub for the latest release; if it is newer it offers to download and
install it.
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .version import APP_NAME, GITHUB_REPO, __version__

API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
FEED = f"https://github.com/{GITHUB_REPO}/releases.atom"


@dataclass
class UpdateInfo:
    version: str
    url: str        # installer download URL
    size: int
    notes: str
    page: str       # release page on GitHub


def vtuple(v):
    return tuple(int(p) if p.isdigit() else 0 for p in str(v).lstrip("vV").split("."))


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"{APP_NAME}/{__version__}"})
    return urllib.request.urlopen(req, timeout=timeout)


def check():
    """Return UpdateInfo if GitHub has a newer release, else None. Raises if GitHub is unreachable.

    Reads the public releases feed: the GitHub API allows only 60 anonymous calls an hour per network address,
    which a whole office behind one Orange address uses up quickly. The API is the fallback.
    """
    try:
        rel = _from_feed()
    except Exception:  # feed unreachable or changed: the API still works when the hourly limit allows
        rel = _from_api()
    if not rel or vtuple(rel.version) <= vtuple(__version__):
        return None
    return rel


def _from_feed():
    with _get(FEED) as r:
        root = ET.fromstring(r.read())
    ns = {"a": "http://www.w3.org/2005/Atom"}
    best = None
    for e in root.findall("a:entry", ns):
        tag = (e.findtext("a:id", "", ns) or "").rsplit("/", 1)[-1]
        version = tag.lstrip("vV")
        if not re.fullmatch(r"\d+(\.\d+)*", version):
            continue
        if best is None or vtuple(version) > vtuple(best.version):
            link = e.find("a:link", ns)
            best = UpdateInfo(version, f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/"
                                       f"SALTO-Buddy-Setup-{version}.exe", 0,
                              _text(e.findtext("a:content", "", ns)), link.get("href", "") if link is not None else "")
    return best


def _from_api():
    with _get(API) as r:
        rel = json.load(r)
    version = rel.get("tag_name", "").lstrip("vV")
    asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".exe")), None)
    if not version or not asset:
        return None
    return UpdateInfo(version, asset["browser_download_url"], asset.get("size", 0),
                      (rel.get("body") or "").strip(), rel.get("html_url", ""))


def _text(html_notes):
    """Release notes (HTML in the feed) as the plain text the update window shows."""
    t = re.sub(r"(?i)<li[^>]*>", "- ", html_notes or "")
    t = re.sub(r"(?i)</(p|li|ul|h\d)>|<br\s*/?>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"\n\s*\n(?=- )", "\n", t)  # list items one per line
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def download(info: UpdateInfo, progress=None):
    """Download the installer to %TEMP%; progress(done_bytes, total_bytes) is called while downloading."""
    path = os.path.join(tempfile.gettempdir(), f"SALTO-Buddy-Setup-{info.version}.exe")
    with _get(info.url, timeout=60) as r, open(path + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or info.size or 0)
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    os.replace(path + ".part", path)
    return path


def run_installer(path):
    """Start the installer detached. The caller must exit right after so files can be replaced."""
    log = os.path.join(tempfile.gettempdir(), "SALTO Buddy update.log")
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", f"/LOG={log}"],
                     close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def frozen():
    return getattr(sys, "frozen", False)
