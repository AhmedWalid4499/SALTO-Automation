"""Plain-language messages for what goes wrong in SALTO/Firefox; the technical details go to error.log only."""
import os
import re
import traceback
from datetime import datetime

from . import config

LOG = os.path.join(config.CONFIG_DIR, "error.log")
# Firefox itself is gone (closed or crashed), not just one tab or page that misbehaved
_GONE = r"Failed to decode response|connection refused|Tried to run command without establishing a connection|InvalidSessionId"

# (pattern in the technical message, what the user reads)
_RULES = [
    (r"not clickable at point|obscures it|screen-layout-mask", "SALTO was still loading."),
    (r"No frame containing \('\((\S+?)\)'", r"SALTO did not open \1 in time."),
    (r"No frame containing", "SALTO did not show the page in time."),
    (r"Not found: .*Commercial Order Ref", "The STC Search page did not open."),
    (r"Not found: .*STC Search", "The SALTO menu did not show 'STC Search'."),
    (r"Unable to locate element|Not found:|no such element", "a part of the page was not shown in SALTO."),
    (r"stale element", "the SALTO page changed while it was being read."),
    (r"[Tt]imed? ?out|TimeoutException", "SALTO took too long to answer."),
    (r"Browsing context has been discarded|no such window|" + _GONE, "Firefox was closed or stopped responding."),
    (r"PermissionError|being used by another process", "a file is open in another program (Excel?)."),
    (r"NS_ERROR_|neterror|dnsNotFound|ERR_NAME_NOT_RESOLVED", "SALTO could not be reached (Orange network / VPN?)."),
]


def clean(text):
    """One short, non-technical line for a technical message."""
    text = str(text or "")
    for pattern, message in _RULES:
        m = re.search(pattern, text)
        if m:
            return m.expand(message) if m.groups() else message
    first = re.sub(r"^Message:\s*", "", text.strip().splitlines()[0] if text.strip() else "")
    first = re.sub(r"^\w+(Exception|Error|Timeout):\s*(Message:\s*)?", "", first.split("; For documentation")[0])
    first = first.strip()[:140]
    return (first if first.endswith((".", "!", "?")) else first + ".") if first else "something unexpected happened."


def browser_gone(exc):
    """Firefox itself is gone (closed, crashed): nothing more can be read until it is started again."""
    return bool(re.search(_GONE, f"{type(exc).__name__}: {exc}"))


def friendly(exc):
    """What the user reads when an action failed."""
    msg = clean(f"{type(exc).__name__}: {exc}")
    return msg[0].upper() + msg[1:] + " Please try again."


def note(exc):
    """For a part that could not be read: keep the details in error.log, return the short line to show."""
    record(exc)
    return clean(f"{type(exc).__name__}: {exc}")


def record(exc):
    """Keep the full technical details in error.log (for support), never on screen."""
    try:
        os.makedirs(config.CONFIG_DIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n"
                    + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except OSError:
        pass
