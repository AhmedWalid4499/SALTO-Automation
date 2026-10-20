"""Dissecting an open SALTO case: every tab, all audit pages, TS devices,
participants, attachments (downloaded) and every sub-case (EQP, CONF, SG...).

Functions expect the driver to be switched into the case's frame
(actions.open_case / open_subcase leave it there).
"""
import base64
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field

from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By

from . import files
from .browser import SaltoBrowser

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract.js"), encoding="utf-8") as _f:
    EXTRACT_JS = _f.read()

CASE_TABS = ["Overview", "TS", "Commercial Content", "Site", "Information", "Attachments", "Audit", "Event"]
SUBCASE_RE = re.compile(r"\(([A-Z]{2,8}-\d{3,})\)\s*$")


@dataclass
class Grid:
    name: str
    headers: list
    rows: list  # list of dicts


@dataclass
class TabData:
    name: str
    sections: list = field(default_factory=list)   # [(section, [(label, value)])]
    grids: list = field(default_factory=list)      # [Grid]
    text: str = ""


@dataclass
class ScopeNode:
    product: str          # e.g. "Managed LAN Services"
    node: str             # e.g. "LAN Switch (39)"
    counts: list          # [(label, value)] e.g. Number of Devices to be added
    devices: Grid         # 'Scope of work only' ticked
    all_devices: Grid = None


@dataclass
class Participant:
    name: str
    role: str
    party: str  # Pega party key, e.g. TechnicalDesignTeam


@dataclass
class Options:
    subcases: bool = True
    downloads: bool = True
    tab_screenshots: bool = False
    folder: str = ""          # order folder (Downloads/ and Screenshots/ go inside)


@dataclass
class CaseData:
    stc_id: str = ""          # case id, e.g. MLAN-215851 or EQP-198834
    title: str = ""           # e.g. "MLAN Modification" / "Order And Deliver"
    stages: list = field(default_factory=list)
    header: list = field(default_factory=list)       # [(label, value)] case header fields
    participants: list = field(default_factory=list)
    scope: list = field(default_factory=list)        # [ScopeNode]
    tabs: dict = field(default_factory=dict)         # tab name -> TabData
    attachments: list = field(default_factory=list)  # dicts incl. 'Saved as'
    screenshots: list = field(default_factory=list)
    subcases: list = field(default_factory=list)     # [CaseData]
    errors: list = field(default_factory=list)

    @property
    def scope_devices(self):
        return [r for n in self.scope for r in n.devices.rows]

    @property
    def all_devices(self):
        return [r for n in self.scope if n.all_devices for r in n.all_devices.rows]

    def walk(self):
        yield self
        for s in self.subcases:
            yield from s.walk()


# ---------------------------------------------------------------- helpers
def _visible_panel(b: SaltoBrowser):
    for p in b.driver.find_elements(By.XPATH, "//*[@role='tabpanel']"):
        with suppress(WebDriverException):
            if p.is_displayed():
                return p
    return None


def _wait_stable(b, timeout=20):
    deadline, last = time.time() + timeout, None
    while time.time() < deadline:
        time.sleep(0.8)
        p = _visible_panel(b)
        txt = p.text if p else ""
        if txt and txt == last and "Loading" not in txt:
            return p
        last = txt
    return _visible_panel(b)


def open_tab(b: SaltoBrowser, name: str):
    tab = b.driver.find_element(By.XPATH, f"//*[@role='tab' and normalize-space(.)='{name}']")
    if tab.get_attribute("aria-selected") != "true":
        tab.click()
    return _wait_stable(b)


def extract(b: SaltoBrowser, root=None) -> dict:
    return b.driver.execute_script(EXTRACT_JS, root) or {}


def _tabdata(name, raw) -> TabData:
    return TabData(
        name=name,
        sections=[(s["name"], [tuple(f) for f in s["fields"]]) for s in raw.get("sections", [])],
        grids=[Grid(g["name"], g["headers"], g["rows"]) for g in raw.get("grids", [])],
        text=raw.get("text", ""),
    )


def tab_names(b):
    return [re.sub(r"\s+", " ", t.text).strip() for t in b.driver.find_elements(By.XPATH, "//*[@role='tab']")
            if t.is_displayed() and t.text.strip()]


def enter_case(b, case_id, timeout=40):
    """Switch the driver into the frame showing this case."""
    b.frame_with_text(f"({case_id})", timeout=timeout)


# ---------------------------------------------------------------- header / participants
_HEADER_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const vis = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
const out = [];
document.querySelectorAll('.field-caption').forEach(c => {
  if (!vis(c) || c.closest('[role=tabpanel]') || c.closest('[data-repeat-source]')) return;
  const v = c.nextElementSibling;
  if (v) out.push([clean(c.textContent), clean(v.textContent)]);
});
return out;
"""


def read_header(b):
    seen, out = set(), []
    for label, value in b.driver.execute_script(_HEADER_JS) or []:
        if label and label not in seen:
            seen.add(label)
            out.append((label, value))
    return out


_PARTICIPANTS_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const out = [];
document.querySelectorAll('[data-repeat-source$="pyWorkParty"] > [role=row], [data-repeat-source$="pyWorkParty"] [base_ref*="pyWorkParty("]').forEach(r => {
  const ref = r.getAttribute('base_ref') || '';
  const m = ref.match(/pyWorkParty\(([^)]*)\)/);
  const a = r.querySelector('a');
  const role = r.querySelector('.supporting_text');
  const name = clean(a && a.textContent);
  if (name && !out.some(o => o.name === name && o.party === (m ? m[1] : '')))
    out.push({name, role: clean(role && role.textContent), party: m ? m[1] : ''});
});
return out;
"""


def read_participants(b):
    return [Participant(p["name"], p["role"], p["party"]) for p in b.driver.execute_script(_PARTICIPANTS_JS) or []]


# ---------------------------------------------------------------- overview tree
_OVERVIEW_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const vis = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
const panel = arguments[0] || document;
const left = [...panel.querySelectorAll('ul.rowContent')].filter(vis).filter(ul => !/(Enter|Click) to sort/.test(ul.textContent) && clean(ul.textContent));
const tbl = [...panel.querySelectorAll('table.gridTable')].filter(vis).find(t => /CaseContentsPage/.test(t.getAttribute('pl_prop') || ''));
let heads = [], right = [];
if (tbl) {
  const trs = [...tbl.querySelectorAll(':scope > tbody > tr')];
  const hr = trs.find(tr => tr.querySelector(':scope > th'));
  heads = hr ? [...hr.querySelectorAll(':scope > th')].map(th => clean(th.textContent).replace(/(Enter|Click) to (sort|filter)/g, '').trim()) : [];
  right = trs.filter(tr => (tr.id || '').startsWith('$PCaseContentsPage'));
}
return left.map((ul, i) => {
  const cells = [...ul.querySelectorAll(':scope > li')];
  const name = clean((cells[1] || cells[0]).textContent);
  const pad = parseInt((ul.getAttribute('style') || '').match(/padding-left:\s*(\d+)/)?.[1] || '0', 10);
  const o = {Name: name, Level: Math.max(0, Math.round((pad - 36) / 18)), _case: (ul.getAttribute('objclass') || '').indexOf('Work') >= 0};
  const tr = right[i];
  if (tr) [...tr.querySelectorAll(':scope > td')].forEach((td, j) => {
    const h = heads[j]; if (h && h !== 'Name') o[h] = clean(td.textContent);
  });
  return o;
});
"""


def read_overview(b):
    """Returns (TabData, [sub-case ids in tree order])."""
    panel = open_tab(b, "Overview")
    rows = b.driver.execute_script(_OVERVIEW_JS, panel) or []
    headers = ["Name", "Assigned To", "Deadline/Completion date", "Urgency", "Status"]
    subs = []
    for r in rows:
        m = SUBCASE_RE.search(r["Name"])
        if r.pop("_case", False) and m and m.group(1) not in subs:
            subs.append(m.group(1))
        r["Name"] = "    " * int(r.pop("Level", 0)) + r["Name"]
        for h in r:
            if h not in headers:
                headers.append(h)
    return TabData("Overview", grids=[Grid("Cases & assignments", headers, rows)] if rows else [],
                   text=panel.text if panel else ""), subs


# ---------------------------------------------------------------- attachments (+ downloads)
_ATTACH_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const panel = arguments[0] || document;
return [...panel.querySelectorAll('[base_ref*="pyAttachments("]')].map(td => {
  const lines = (td.innerText || '').split('\n').map(clean).filter(Boolean);
  // the info line "<case> | <category> | <by> | <date>" is the LAST piped line (titles can contain '|')
  const meta = lines.filter(l => (l.match(/\|/g) || []).length >= 3).pop() || '';
  const parts = meta.split('|').map(clean);
  const a = td.querySelector('a.Case_tools');
  const title = clean(a && a.getAttribute('title')) || clean(a && a.textContent) || lines.filter(l => l !== meta).join(' ');
  return {Title: title, Case: parts[0] || '', Category: parts[1] || '', 'Added by': parts[2] || '', Date: parts[3] || ''};
});
"""


def read_attachments(b, case_id, opts: Options, log=print):
    panel = open_tab(b, "Attachments")
    rows = b.driver.execute_script(_ATTACH_JS, panel) or []
    if opts.downloads and opts.folder and rows:
        dest = files.sub(opts.folder, "Downloads", case_id)
        for i, row in enumerate(rows):
            log(f"Downloading {case_id} attachment {i + 1}/{len(rows)}: {row['Title'][:50]}")
            try:
                row["Saved as"] = _download_one(b, case_id, i, row, dest)
            except (WebDriverException, OSError) as exc:
                row["Saved as"] = f"failed: {str(exc).splitlines()[0][:80]}"
                with suppress(WebDriverException):
                    _back_to_case(b, case_id)
    return TabData("Attachments", grids=[Grid("Attachments", ["Title", "Category", "Added by", "Date", "Case", "Saved as"]
                                              if opts.downloads else ["Title", "Category", "Added by", "Date", "Case"], rows)]
                   if rows else [], text=panel.text if panel else ""), rows


def _back_to_case(b, case_id):
    d = b.driver
    main = d.window_handles[0]
    for h in d.window_handles[1:]:
        with suppress(WebDriverException):
            d.switch_to.window(h)
            d.close()
    d.switch_to.window(main)
    enter_case(b, case_id)
    open_tab(b, "Attachments")


def _download_one(b, case_id, index, row, dest):
    """Click attachment `index` (only its name link: never the delete icon) and save what it yields."""
    d = b.driver
    cells = _visible_panel(b).find_elements(By.XPATH, ".//*[contains(@base_ref,'pyAttachments(')]")
    links = cells[index].find_elements(By.XPATH, ".//a[contains(@class,'Case_tools')]") if index < len(cells) else []
    if not links:
        return "not found"
    before_files, before_windows = files.staged(), set(d.window_handles)
    # the name link can be zero-sized (no title): fire its own click handler instead of a mouse click
    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", links[0])
    # "<title> <date>": unique within a case, and a re-run overwrites instead of piling up copies
    stem = files.safe(f"{row['Title'] or row.get('Category') or 'Attachment'} {row.get('Date', '')}".replace(":", ""), 80)
    saved = ""
    deadline = time.time() + 25
    while time.time() < deadline and not saved:
        f = files.wait_new_download(before_files, timeout=1.5)
        if f:
            saved = files.replace_into(f, dest, stem + os.path.splitext(f)[1])
            break
        for h in set(d.window_handles) - before_windows:   # opened in a window (e.g. View Email)
            d.switch_to.window(h)
            time.sleep(2.5)
            if d.current_url.startswith("about:blank"):
                continue
            path = os.path.join(dest, stem + ".pdf")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(d.print_page()))
            saved = path
            break
    # a file download can still leave an empty window behind: close every extra window
    f = files.wait_new_download(before_files, timeout=1) if not saved else None
    if f:
        saved = files.replace_into(f, dest, stem + os.path.splitext(f)[1])
    _back_to_case(b, case_id)
    return saved or "nothing to download"


# ---------------------------------------------------------------- audit (all pages)
def read_audit(b, log=print, max_pages=60):
    panel = open_tab(b, "Audit")
    raw = extract(b, panel)
    grids = [g for g in raw.get("grids", []) if "Description" in g["headers"]] or raw.get("grids", [])
    if not grids:
        return _tabdata("Audit", raw)
    g = grids[0]
    rows, seen = list(g["rows"]), {repr(r) for r in g["rows"]}
    for page in range(2, max_pages + 1):
        nxt = [x for x in panel.find_elements(By.XPATH, ".//button[@title='Next Page']") if x.is_displayed()]
        if not nxt:
            break
        log(f"Audit page {page}...")
        first = repr(rows[-1]) if rows else ""
        b.driver.execute_script("arguments[0].click()", nxt[0])
        panel = _wait_stable(b, timeout=15)
        new = [gg for gg in extract(b, panel).get("grids", []) if gg["headers"] == g["headers"]]
        fresh = [r for r in (new[0]["rows"] if new else []) if repr(r) not in seen]
        if not fresh:
            break
        rows += fresh
        seen.update(repr(r) for r in fresh)
        if first and repr(fresh[-1]) == first:
            break
    with suppress(WebDriverException):  # back to page 1 for the user
        for x in panel.find_elements(By.XPATH, ".//button[@title='First Page']"):
            if x.is_displayed():
                b.driver.execute_script("arguments[0].click()", x)
                break
    return TabData("Audit", grids=[Grid("History (all pages)", g["headers"], rows)], text=raw.get("text", ""))


# ---------------------------------------------------------------- TS devices
_TS_NODES_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const vis = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
const panel = arguments[0] || document;
let product = '';
const out = [];
[...panel.querySelectorAll('ul.rowContent')].filter(vis).forEach((ul, i) => {
  const name = clean(ul.textContent);
  if (!name) return;
  if (/\(\d+\)$/.test(name)) out.push({product, node: name, index: i});
  else product = name;
});
return out;
"""


def _scope_checkbox(b):
    lab = b.driver.find_element(By.XPATH, "//label[normalize-space(.)='Scope of work only']")
    return lab, b.driver.find_element(By.ID, lab.get_attribute("for"))


def _device_grid(b):
    raw = extract(b, _visible_panel(b))
    counts = [tuple(f) for s in raw.get("sections", []) for f in s["fields"] if f[0].startswith("Number of")]
    grids = [g for g in raw.get("grids", []) if "USID" in g["headers"] or "Name" in g["headers"]]
    g = grids[0] if grids else {"headers": [], "rows": []}
    return counts, g


def _set_scope(b, on):
    lab, cb = _scope_checkbox(b)
    if cb.is_selected() != on:
        lab.click()
        _wait_stable(b)


def read_ts(b, log=print):
    """Each TS product node: all devices, then with 'Scope of work only' ticked."""
    panel = open_tab(b, "TS")
    nodes = b.driver.execute_script(_TS_NODES_JS, panel) or []
    result = []
    for n in nodes:
        log(f"TS: {n['product']} > {n['node']}...")
        el = [e for e in b.driver.find_elements(By.XPATH, "//*[@role='tabpanel']//ul[contains(@class,'rowContent')]")
              if e.is_displayed()][n["index"]]
        target = el.find_elements(By.XPATH, ".//div[contains(@class,'oflowDiv')]")
        target = target[-1] if target else el
        b.driver.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
        target.click()
        _wait_stable(b)
        all_g, scope_g, counts = {"headers": [], "rows": []}, {"headers": [], "rows": []}, []
        try:
            _, cb = _scope_checkbox(b)
            was = cb.is_selected()
            _set_scope(b, False)
            counts, all_g = _device_grid(b)
            _set_scope(b, True)
            counts2, scope_g = _device_grid(b)
            counts = counts2 or counts
            _set_scope(b, was)  # leave SALTO as we found it
        except NoSuchElementException:
            counts, all_g = _device_grid(b)
        result.append(ScopeNode(n["product"], n["node"], counts,
                                Grid("Scope of work devices", scope_g["headers"], scope_g["rows"]),
                                Grid("All devices", all_g["headers"], all_g["rows"])))
    return result


# ---------------------------------------------------------------- sub-cases
def open_subcase(b, parent_id, sub_id):
    """From the parent case's Overview tree, open a sub-case (it opens in its own SALTO tab)."""
    if _focus_case_tab(b, sub_id):  # already open: reopening would prompt "lose unsaved changes?"
        enter_case(b, sub_id, timeout=60)
        return
    _focus_case_tab(b, parent_id)
    enter_case(b, parent_id)
    open_tab(b, "Overview")
    link = [a for a in b.driver.find_elements(By.XPATH, f"//*[@role='tabpanel']//a[contains(normalize-space(.), '({sub_id})')]")
            if a.is_displayed()]
    if not link:
        raise NoSuchElementException(f"link to {sub_id} not found")
    b.driver.execute_script("arguments[0].scrollIntoView({block:'center'})", link[0])
    link[0].click()
    enter_case(b, sub_id, timeout=60)
    time.sleep(1.5)


def close_case_tab(b, case_id):
    d = b.driver
    d.switch_to.default_content()
    for li in d.find_elements(By.XPATH, f"//li[@role='tab' and starts-with(@aria-label, '{case_id} ')]"):
        for x in li.find_elements(By.XPATH, ".//span[contains(@class,'iconCloseSmall')]"):
            d.execute_script("arguments[0].click()", x)
            time.sleep(1.5)
            return True
    return False


# ---------------------------------------------------------------- one case
def read_case(b: SaltoBrowser, case_id: str, opts: Options = None, log=print, read_stages=None, depth=0) -> CaseData:
    opts = opts or Options()
    data = CaseData(stc_id=case_id, title=re.sub(rf"\s*{re.escape(case_id)}\s*$", "", b.driver.title))
    if read_stages:
        data.stages = read_stages(b)
    data.header = read_header(b)
    data.participants = read_participants(b)
    names = tab_names(b) or CASE_TABS
    sub_ids = []
    for name in names:
        log(f"{case_id}: reading {name}...")
        try:
            if name == "Overview":
                data.tabs[name], sub_ids = read_overview(b)
            elif name == "Attachments":
                data.tabs[name], data.attachments = read_attachments(b, case_id, opts, log)
            elif name == "Audit":
                data.tabs[name] = read_audit(b, log)
            elif name == "TS" and depth > 0:
                continue  # a sub-case's TS repeats the parent's device tree: read once, on the main case
            elif name == "TS":
                nodes = read_ts(b, log)
                if depth == 0 or any(n.devices.rows or (n.all_devices and n.all_devices.rows) for n in nodes):
                    data.scope = nodes
                td = TabData("TS")
                for n in nodes:
                    td.sections.append((f"{n.product} > {n.node}", n.counts))
                    if n.devices.rows:
                        td.grids.append(Grid(f"{n.node} - scope of work", n.devices.headers, n.devices.rows))
                    if n.all_devices and n.all_devices.rows:
                        td.grids.append(Grid(f"{n.node} - all devices", n.all_devices.headers, n.all_devices.rows))
                data.tabs[name] = td
            else:
                panel = open_tab(b, name)
                raw = extract(b, panel)
                td = _tabdata(name, raw)
                for sub in [s for s in raw.get("subtabs", []) if s not in names]:   # tabs inside a tab
                    with suppress(WebDriverException):
                        sp = open_tab(b, sub)
                        st = _tabdata(sub, extract(b, sp))
                        td.sections += [(f"{sub} / {s}", f) for s, f in st.sections]
                        td.grids += [Grid(f"{sub} / {g.name}", g.headers, g.rows) for g in st.grids]
                    open_tab(b, name)
                data.tabs[name] = td
            if opts.tab_screenshots and opts.folder:
                shot = files.numbered(files.sub(opts.folder, "Screenshots"), f"{case_id}_{name}")
                b.driver.switch_to.default_content()
                b.driver.save_screenshot(shot)
                data.screenshots.append(shot)
                enter_case(b, case_id)
        except (WebDriverException, IndexError) as exc:
            msg = f"{case_id} / {name}: {str(exc).splitlines()[0][:120]}"
            log("  could not read " + msg)
            data.errors.append(msg)
            with suppress(WebDriverException):
                enter_case(b, case_id, timeout=15)

    if opts.subcases and depth == 0:
        for i, sid in enumerate(sub_ids, 1):
            log(f"Sub-case {i}/{len(sub_ids)}: {sid}...")
            try:
                open_subcase(b, case_id, sid)
                data.subcases.append(read_case(b, sid, opts, log, read_stages, depth + 1))
            except WebDriverException as exc:
                data.errors.append(f"{sid}: {str(exc).splitlines()[0][:120]}")
                log(f"  could not open {sid}")
            finally:
                with suppress(WebDriverException):
                    close_case_tab(b, sid)
                with suppress(WebDriverException):
                    _focus_case_tab(b, case_id)
                    enter_case(b, case_id)
    with suppress(WebDriverException):
        enter_case(b, case_id, timeout=15)
        open_tab(b, "Overview")
    return data


def _focus_case_tab(b, case_id):
    d = b.driver
    d.switch_to.default_content()
    for li in d.find_elements(By.XPATH, f"//li[@role='tab' and starts-with(@aria-label, '{case_id} ')]"):
        if li.get_attribute("aria-selected") != "true":
            li.click()
            time.sleep(1.5)
        return True
    return False
