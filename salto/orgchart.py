"""Orange Business OrgChart: a person's email, job and manager (with the manager's email).

Uses the OrgChart's own search (the same request as its Search button) inside a Firefox tab signed in with the
Orange SSO, so nothing else is needed. Results are kept a week on disk: people rarely change manager.
"""
import json
import os
import re
import time
from contextlib import suppress
from urllib.parse import urlparse

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By

from . import config

HOME = "https://obs-orgchart.sso.infra.ftgroup/dashboard/home"
HOST = "obs-orgchart.sso.infra.ftgroup"
CACHE = os.path.join(config.CONFIG_DIR, "cache", "orgchart.json")
KEEP_DAYS = 7
# SALTO participants that are not people
NOT_PEOPLE = re.compile(r"^(salto\b|service level agent|system|batch|admin|unassigned)", re.I)

_SEARCH_JS = r"""
const cb = arguments[arguments.length - 1];
const [last, first, email, cuid] = arguments;
$.ajax({url: '/ooc_staff/search/', type: 'POST', timeout: 30000,
  data: {csrfmiddlewaretoken: getCSRFToken(), firstName: first, lastName: last, email: email, cuid: cuid},
  success: j => cb({ok: j.empl || []}), error: x => cb({err: x.status})});
"""

# what is kept from an OrgChart record, and its label
FIELDS = [("display_name", "Name"), ("email", "Email"), ("busi_title", "Job title"), ("dept_desc", "Department"),
          ("country_descr", "Country"), ("city", "City"), ("phone", "Phone"), ("mobile", "Mobile"),
          ("vendor_name", "Vendor"), ("supr_display_name", "Manager"), ("supr_cuid", "Manager CUID"),
          ("cuid", "CUID")]


def _person(rec):
    return {k: (rec.get(k) or "").strip() for k, _ in FIELDS}


# ---------------------------------------------------------------- cache
def _load():
    with suppress(OSError, ValueError):
        data = json.load(open(CACHE, encoding="utf-8"))
        cutoff = time.time() - KEEP_DAYS * 86400
        return {k: v for k, v in data.items() if v.get("saved", 0) > cutoff}
    return {}


def _save(data):
    with suppress(OSError):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(CACHE + ".tmp", CACHE)


# ---------------------------------------------------------------- browser
class OrgChart:
    """One OrgChart tab next to SALTO; every call returns to the tab that was active before."""

    def __init__(self, b, log=print):
        self.b, self.log = b, log
        self.handle = None

    def __enter__(self):
        self.back = self.b.driver.current_window_handle
        self._open()
        return self

    def __exit__(self, *exc):
        d = self.b.driver
        with suppress(WebDriverException):
            if self.handle in d.window_handles:
                d.switch_to.window(self.handle)
                d.close()
        with suppress(WebDriverException):
            d.switch_to.window(self.back)

    def _open(self):
        d = self.b.driver
        d.switch_to.new_window("tab")
        self.handle = d.current_window_handle
        d.set_page_load_timeout(60)
        with suppress(TimeoutException):
            d.get(HOME)
        deadline = time.time() + 90
        shown = False
        while time.time() < deadline:
            self._acknowledge()
            with suppress(WebDriverException):
                if urlparse(d.current_url).hostname == HOST and d.execute_script(
                        "return typeof getCSRFToken === 'function' && typeof $ !== 'undefined'"):
                    return
            if not shown and time.time() > deadline - 60 and not self.b.visible:
                # stuck on an Orange sign-in page: let the user finish it
                self.log("The Org Chart needs you to sign in: opening the Firefox window...")
                with suppress(Exception):
                    self.b.set_visible(True)
                shown = True
            time.sleep(1)
        raise RuntimeError("The Org Chart did not open (Orange network / sign-in?).")

    def _acknowledge(self):
        """Click the OrgChart's acknowledgement / consent button when it asks for it."""
        d = self.b.driver
        with suppress(WebDriverException):
            for el in d.find_elements(By.XPATH, "//button | //a[contains(@class,'btn')] | //input[@type='submit']"):
                text = (el.text or el.get_attribute("value") or "").strip()
                if el.is_displayed() and re.search(r"acknowledg|^i agree|^accept|^i understand", text, re.I):
                    d.execute_script("arguments[0].click();", el)
                    time.sleep(1.5)
                    return

    def search(self, last="", first="", email="", cuid=""):
        d = self.b.driver
        d.switch_to.window(self.handle)
        d.set_script_timeout(40)
        r = d.execute_async_script(_SEARCH_JS, last, first, email, cuid) or {}
        if "err" in r:
            raise RuntimeError(f"The Org Chart search failed (HTTP {r['err']}).")
        return r.get("ok", [])


def _variants(name):
    """(last, first) guesses for a SALTO display name: 'Ahmed El-Bourgy', 'Linh Le Nu Dieu', 'KANADE Rahul'."""
    parts = [p for p in re.split(r"\s+", name.replace(",", " ").strip()) if p]
    if len(parts) < 2:
        return [(parts[0], "")] if parts else []
    out = [(" ".join(parts[1:]), parts[0]), (parts[-1], " ".join(parts[:-1])), (parts[-1], parts[0]),
           (parts[0], " ".join(parts[1:]))]
    return list(dict.fromkeys(out))


def _best(name, found):
    """The OrgChart record(s) that really are this person (same first and last name words)."""
    want = {w for w in re.split(r"[\s,.-]+", name.lower()) if w}
    def score(rec):
        have = {w for w in re.split(r"[\s,.-]+", " ".join(
            [str(rec.get(k) or "") for k in ("display_name", "legalFirstName", "legalLastName")]).lower()) if w}
        return len(want & have)
    if not found:
        return []
    top = max(score(r) for r in found)
    return [r for r in found if score(r) == top and top >= min(2, len(want))]


def lookup(b, names, log=print, refresh=False):
    """{name: {'person': {...} or None, 'manager': {...} or None, 'matches': n, 'note': str}} for SALTO names."""
    cache = {} if refresh else _load()
    todo = [n for n in dict.fromkeys(names) if n and not NOT_PEOPLE.match(n) and n not in cache]
    if todo:
        log(f"Org Chart: looking up {len(todo)} person(s)...")
        with OrgChart(b, log) as oc:
            managers = {}
            for name in todo:
                hits = []
                for last, first in _variants(name):
                    hits = _best(name, oc.search(last, first))
                    if hits:
                        break
                entry = {"person": None, "manager": None, "matches": len(hits), "saved": time.time(),
                         "note": "" if len(hits) == 1 else ("not found in the Org Chart" if not hits else
                                                            f"{len(hits)} people with this name: the first is shown")}
                if hits:
                    entry["person"] = _person(hits[0])
                    sup = entry["person"]["supr_cuid"]
                    if sup:
                        if sup not in managers:
                            got = oc.search(cuid=sup)
                            managers[sup] = _person(got[0]) if got else None
                        entry["manager"] = managers[sup]
                cache[name] = entry
        _save({**_load(), **cache})
    return {n: cache[n] for n in dict.fromkeys(names) if n in cache}


def find(b, last="", first="", email="", levels=6, log=print):
    """Search like the OrgChart page: every match, each with its management chain (manager first)."""
    with OrgChart(b, log) as oc:
        hits = oc.search(last, first, email)
        people = []
        seen = {}
        for rec in hits[:15]:
            p, chain, cuid = _person(rec), [], rec.get("supr_cuid")
            while cuid and len(chain) < levels and cuid not in [c["cuid"] for c in chain]:
                if cuid not in seen:
                    got = oc.search(cuid=cuid)
                    seen[cuid] = _person(got[0]) if got else None
                if not seen[cuid]:
                    break
                chain.append(seen[cuid])
                cuid = seen[cuid]["supr_cuid"]
            p["chain"] = chain
            people.append(p)
        return people
