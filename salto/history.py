"""A one-line summary of every order read, for the Home dashboard (%APPDATA%\\SALTO Buddy\\history.json).

Kept separately from the saved copies (cache): those are tied to an app version and large, this is small and
survives updates.
"""
import json
import os
import pickle
import time
from contextlib import suppress

from .config import CONFIG_DIR

PATH = os.path.join(CONFIG_DIR, "history.json")


def summary(rep, read_at=None):
    case = rep.case
    devices = case.scope_devices if case else []
    creation = [d for d in devices if (d.get("Cycle") or "").lower() == "creation"]
    cessation = [d for d in devices if (d.get("Cycle") or "").lower() == "cessation"]
    serials = [s for c in (case.walk() if case else []) for s in (c.flip or {}).get("serials", [])]
    subs = case.subcases if case else []
    open_subs = [s for s in subs if s.stages and not all(x.state == "completed" for x in s.stages)]
    header = dict(case.header) if case else {}
    site = {}
    if case and case.tabs.get("Site"):
        for _, fields in case.tabs["Site"].sections:
            site.update({k: v for k, v in fields})
    types = {}
    for d in creation:
        t = d.get("Type") or "Other"
        types[t] = types.get(t, 0) + 1
    return {
        "order": rep.order_ref, "stc": rep.stc_id, "customer": header.get("Customer name", ""),
        "product": header.get("Product", ""), "status": rep.status, "stage": rep.current_stage,
        "target": header.get("Target Delivery Date", ""), "city": site.get("City", ""),
        "country": site.get("Country", ""), "creation": len(creation), "cessation": len(cessation),
        "scope": len(devices), "types": types,
        "serials_found": sum(1 for s in serials if s.get("Serial number")), "serials_total": len(serials),
        "subcases": len(subs), "open_subcases": len(open_subs),
        "attachments": sum(len(c.attachments) for c in case.walk()) if case else 0,
        "pulse": sum(len(getattr(c, "pulse", []) or []) for c in case.walk()) if case else 0,
        "read": read_at or time.time(),
    }


def load():
    with suppress(OSError, ValueError):
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def record(rep):
    if not rep or not rep.stc_id or not rep.case:
        return
    data = load()
    data[rep.order_ref] = summary(rep)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(PATH + ".tmp", PATH)


def seed_from_cache():
    """First run: build the history from the saved copies already on this PC (any app version)."""
    from .cache import CACHE_DIR
    data = load()
    changed = False
    with suppress(OSError):
        for name in os.listdir(CACHE_DIR):
            if not name.endswith(".pkl"):
                continue
            try:
                with open(os.path.join(CACHE_DIR, name), "rb") as f:
                    saved = pickle.load(f)
                rep = saved["rep"]
                if rep.order_ref not in data and rep.case:
                    data[rep.order_ref] = summary(rep, saved.get("saved"))
                    changed = True
            except Exception:  # a copy from an older app version that no longer loads: skip it
                continue
    if changed:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(PATH + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(PATH + ".tmp", PATH)
    return data


def orders():
    """Summaries, most recently read first."""
    return sorted(load().values(), key=lambda r: r.get("read", 0), reverse=True)
