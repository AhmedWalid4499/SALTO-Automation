"""FLIP serial numbers for the EQP sub-cases of an order.

For each device in an EQP's Information tab, the rocket icon opens SALTO's
'Delivery info' pop-up with the FLIP Intervention Id. In FLIP (opened in a new
tab of the same hidden Firefox, signed in by single sign-on) the app opens
Work Flow Action Items > Open Part Request, reads the part list and saves
FLIP's Export. Each SALTO device is then matched to its FLIP part: same OBS
device name (FLIP 'routerName') and a part number matching the device model,
so the switch itself is picked, not its power supplies or SFPs.

Read-only: only the rocket pop-up (closed again), 'Open Part Request' and
'Export' are ever clicked - never FLIP's other actions (Close, Yank, Edit...).
"""
import json
import os
import re
import time
from contextlib import suppress

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By

from . import files

# capture FLIP's own part-list API answers (the table paginator is unreliable)
_HOOK_JS = r"""
if (!window.__sbHooked) {
  window.__sbWO = {};
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m, url) { this.__sbUrl = url; return open.apply(this, arguments); };
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function() {
    this.addEventListener('load', () => {
      if (/workOrderDetail/.test(this.__sbUrl || '')) window.__sbWO[this.__sbUrl] = this.responseText;
    });
    return send.apply(this, arguments);
  };
  window.__sbHooked = true;
}
"""

_MODAL_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const m = [...document.querySelectorAll('[role=dialog], [id*=modaldialog], .modal-dialog')].find(e => e.offsetWidth);
if (!m) return null;
const fields = {};
m.querySelectorAll('.field-caption, .dataLabelForRead').forEach(c => {
  const v = c.nextElementSibling; if (v) fields[clean(c.textContent)] = clean(v.textContent);
});
const links = {};
m.querySelectorAll('a[href*="flip."]').forEach(a => { links[clean(a.textContent)] = a.href; });
return {fields, links};
"""


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _model_matches(part_number, model):
    """CIS-C9500-48Y4C-A matches C9500-48Y4C-A (vendor prefix on the FLIP side)."""
    p, m = norm(part_number), norm(model)
    return bool(m) and (p == m or p.endswith(m))


# ---------------------------------------------------------------- SALTO side: rocket pop-ups
def read_rockets(b, eqp_id, log=print):
    """In the EQP's Information tab: open each device's rocket pop-up, read it, close it."""
    from .case import _visible_panel, enter_case, open_tab
    enter_case(b, eqp_id)
    open_tab(b, "Information")
    d = b.driver
    icons = [a for a in _visible_panel(b).find_elements(By.XPATH, ".//a[contains(@class,'iconDefault')]")
             if a.is_displayed() and "DeliveryInfo" in (a.get_attribute("data-click") or "")]
    out = []
    for i in range(len(icons)):
        icons = [a for a in _visible_panel(b).find_elements(By.XPATH, ".//a[contains(@class,'iconDefault')]")
                 if a.is_displayed() and "DeliveryInfo" in (a.get_attribute("data-click") or "")]
        if i >= len(icons):
            break
        d.execute_script("arguments[0].scrollIntoView({block:'center'})", icons[i])
        icons[i].click()
        info = None
        for _ in range(20):
            time.sleep(0.5)
            info = _first_modal(b)
            if info:
                break
        if not info:
            log(f"  {eqp_id}: the rocket pop-up did not open for device {i + 1}")
            continue
        f = info["fields"]
        out.append({"EQP": eqp_id, "Device": f.get("Device Name", ""), "Model": f.get("Device Model", ""),
                    "USID": f.get("Device USID", ""), "CDC": f.get("Customer Defined Code", ""),
                    "Device Type": f.get("Device Type", ""), "SALTO serial": f.get("Serial Number", ""),
                    "Intervention": f.get("Intervention Id", ""),
                    "Part request": f.get("Installation Part Request Number", ""),
                    "FLIP link": next((u for t, u in info["links"].items() if t == f.get("Intervention Id")), "")})
        _close_modal(b)
        enter_case(b, eqp_id)
    return out


def _first_modal(b):
    for _ in b.frames():
        with suppress(WebDriverException):
            info = b.driver.execute_script(_MODAL_JS)
            if info:
                return info
    return None


def _close_modal(b):
    for _ in b.frames():
        for x in b.driver.find_elements(By.XPATH, "//button[@title='Close modal']"):
            with suppress(WebDriverException):
                if x.is_displayed():
                    x.click()
                    time.sleep(1)
                    return


# ---------------------------------------------------------------- FLIP side
def fetch_parts(b, url, save_dir="", label="", log=print, timeout=90):
    """Open a FLIP intervention in a new tab, Open Part Request, read every part, Export. Returns (parts, export)."""
    d = b.driver
    salto_tab = d.current_window_handle
    d.switch_to.new_window("tab")
    try:
        d.set_page_load_timeout(60)
        with suppress(TimeoutException):
            d.get(url)
        deadline = time.time() + timeout
        menu = None
        while time.time() < deadline and not menu:  # FLIP is an Angular app: wait for the action menu
            time.sleep(1.5)
            # the menu button inside the innermost element labelled 'Work Flow Action Items' (not FLIP's other menus)
            for e in d.find_elements(By.XPATH, "//*[contains(normalize-space(text()),'Work Flow Action Items')]"
                                               "/ancestor-or-self::*[.//button[contains(@class,'mat-menu-trigger')]][1]"
                                               "//button[contains(@class,'mat-menu-trigger')]"):
                if e.is_displayed():
                    menu = e
        if not menu:
            raise RuntimeError("FLIP did not load (no 'Work Flow Action Items')")
        d.execute_script(_HOOK_JS)
        item = []
        for _ in range(10):  # FLIP may still be covering the page while it loads: retry until the menu opens
            d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", menu)
            time.sleep(1.5)
            item = [m for m in d.find_elements(By.XPATH, "//*[@role='menuitem']")
                    if m.is_displayed() and m.text.strip() == "Open Part Request"]
            if item:
                break
        if not item:
            raise RuntimeError("FLIP menu has no 'Open Part Request'")
        d.execute_script("arguments[0].click();", item[0])
        parts = _collect(d, timeout=40)
        export = ""
        if save_dir:
            try:  # the Excel copy is a bonus: never lose the serial numbers over it
                export = _export(b, save_dir, label)
            except (OSError, WebDriverException) as exc:
                log(f"FLIP export not saved: {str(exc).splitlines()[0][:120]}")
        return parts, export
    finally:
        with suppress(WebDriverException):
            d.close()
        d.switch_to.window(salto_tab)


def _collect(d, timeout):
    """Read the part list answers, paging with FLIP's own Next button while it returns new parts."""
    deadline = time.time() + timeout
    while time.time() < deadline and not d.execute_script("return Object.keys(window.__sbWO || {}).length"):
        time.sleep(1)
    # the whole list in one call: same API FLIP uses, with a page big enough for every part
    first = next(iter(d.execute_script("return Object.keys(window.__sbWO || {})") or []), "")
    if first:
        url = re.sub(r"pageSize=\d+", "pageSize=2000", re.sub(r"pageNumber=\d+", "pageNumber=0", first))
        body = d.execute_async_script("""const cb = arguments[arguments.length - 1];
          fetch(arguments[0], {credentials: 'include'}).then(r => r.ok ? r.text() : '').then(cb).catch(() => cb(''));""",
                                      url)
        with suppress(ValueError, TypeError):
            if isinstance(json.loads(body), list):
                d.execute_script("window.__sbWO[arguments[0]] = arguments[1];", url, body)
                return _parts(d)
    for _ in range(10):  # next pages (FLIP sometimes repeats page 1: stop when nothing new comes)
        n_before = d.execute_script("return Object.keys(window.__sbWO).length")
        clicked = d.execute_script(r"""
          const th = [...document.querySelectorAll('th')].find(t => t.offsetWidth && t.textContent.trim() === 'Serial Number');
          let box = th && th.closest('table');
          while (box && !box.querySelector('mat-paginator')) box = box.parentElement;
          const n = box && box.querySelector('mat-paginator button[aria-label="Next page"]');
          if (!n || n.disabled) return false; n.click(); return true;""")
        if not clicked:
            break
        t = time.time()
        while time.time() - t < 8 and d.execute_script("return Object.keys(window.__sbWO).length") == n_before:
            time.sleep(0.5)
    return _parts(d)


def _parts(d):
    """Every part from the captured answers, once each."""
    parts = {}
    for body in (d.execute_script("return window.__sbWO") or {}).values():
        with suppress(ValueError):
            for p in json.loads(body) or []:
                parts.setdefault(p.get("resourceItem") or json.dumps(p, sort_keys=True), p)
    return list(parts.values())


def _export(b, save_dir, label):
    """Click FLIP's Export and keep the Excel in the order folder."""
    d = b.driver
    btn = [x for x in d.find_elements(By.XPATH, "//button[normalize-space(.)='Export']") if x.is_displayed()]
    if not btn:
        return ""
    before = files.staged()
    btn[0].click()
    f = files.wait_new_download(before, timeout=30)
    return files.replace_into(f, save_dir, files.safe(f"FLIP parts {label}", 70) + os.path.splitext(f)[1]) if f else ""


# ---------------------------------------------------------------- everything for one EQP
def part_row(p):
    sn = p.get("serialNumber")
    serial = (sn[0] if sn else "") if isinstance(sn, list) else (sn or "")
    serial = serial or p.get("proposedSerialNumber") or ""
    return {"Device": p.get("routerName", ""), "Part number": p.get("partNumber", ""),
            "Description": p.get("description", ""), "Serial number": serial, "Status": p.get("status", ""),
            "Condition": p.get("condition", ""), "Request": p.get("resourceItem", ""),
            "Type": p.get("requestType", ""), "Revision": p.get("revision", ""), "Created": p.get("createDate", "")}


def match(devices, parts):
    """Serial number of each SALTO device: its FLIP part with the device's model (the device itself)."""
    rows = [part_row(p) for p in parts]
    usable = [r for r in rows if "CANCEL" not in r["Status"].upper()]
    out = []
    for dev in devices:
        # the device's own part request (from the rocket) when it is the device itself (FLIP's router name can
        # be wrong), else the parts FLIP lists under the device name
        by_request = [r for r in usable if dev.get("Part request") and norm(r["Request"]) == norm(dev["Part request"])]
        by_name = [r for r in usable if norm(r["Device"]) == norm(dev["Device"])]
        main = [r for r in by_request if _model_matches(r["Part number"], dev["Model"])] or \
               [r for r in by_name if _model_matches(r["Part number"], dev["Model"])] or \
               [r for r in by_name if r["Revision"].upper().endswith("-RF")]
        hit = dict(main[0]) if main else {}
        serials = list(dict.fromkeys(r["Serial number"] for r in main if r["Serial number"]))
        if len(serials) > 1:  # FLIP cannot tell which one: show them all
            hit["Serial number"] = " / ".join(serials)
        out.append({"EQP": dev["EQP"], "Device (OBS name)": dev["Device"], "CDC": dev["CDC"], "USID": dev["USID"],
                    "Model": dev["Model"], "Serial number": hit.get("Serial number", ""),
                    "FLIP part number": hit.get("Part number", ""), "FLIP status": hit.get("Status", ""),
                    "Condition": hit.get("Condition", ""), "Part request": hit.get("Request", ""),
                    "Intervention": dev["Intervention"],
                    "Check": ("OK" if len(main) == 1 or len(serials) == 1 else f"{len(main)} matching parts - check"
                              if main
                              else "no matching device part in FLIP")})
    return out, rows


def read_eqp(b, eqp_id, folder="", log=print):
    """Returns {'serials': [...], 'parts': [...], 'exports': [...], 'errors': [...]} for one EQP sub-case."""
    result = {"serials": [], "parts": [], "exports": [], "errors": []}
    log(f"{eqp_id}: reading FLIP links (rocket)...")
    devices = read_rockets(b, eqp_id, log)
    if not devices:
        result["errors"].append(f"{eqp_id}: no device with a FLIP intervention found")
        return result
    parts, seen = [], set()
    for dev in devices:
        url = dev["FLIP link"]
        if not url or dev["Intervention"] in seen:
            continue
        seen.add(dev["Intervention"])
        log(f"{eqp_id}: FLIP intervention {dev['Intervention']} - Open Part Request...")
        try:
            got, export = fetch_parts(b, url, files.sub(folder, "Downloads", "FLIP") if folder else "",
                                      f"{eqp_id} {dev['Intervention']}", log)
            parts += got
            if export:
                result["exports"].append(export)
        except (WebDriverException, RuntimeError, OSError) as exc:
            result["errors"].append(f"{eqp_id} / FLIP {dev['Intervention']}: {str(exc).splitlines()[0][:120]}")
    from .case import enter_case
    with suppress(WebDriverException):
        enter_case(b, eqp_id)
    result["serials"], result["parts"] = match(devices, parts)
    log(f"{eqp_id}: {sum(1 for s in result['serials'] if s['Serial number'])} of {len(devices)} serial number(s) found")
    return result
