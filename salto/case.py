"""Dissecting an open SALTO case: every tab, all audit pages, TS devices,
participants, attachments (downloaded) and every sub-case (EQP, CONF, SG...).

Functions expect the driver to be switched into the case's frame
(actions.open_case / open_subcase leave it there).
"""
import base64
import json
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field

from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By

from . import errors, files
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
    extra: list = field(default_factory=list)  # other tables shown with the devices (EQUIPMENT INFORMATION...)


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
    flip: bool = True         # FLIP serial numbers for EQP sub-cases
    full_audit: bool = False  # every audit page (slow); otherwise the latest page only
    later_subcases: bool = False  # read the main case only; read_subcases() does the rest afterwards
    folder: str = ""          # order folder (Downloads/ and Screenshots/ go inside)
    cancel: object = None     # threading.Event: stop reading sub-cases (another order was opened)


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
    flip: dict = field(default_factory=dict)         # EQP only: {'serials', 'parts', 'exports', 'errors'}
    pending_subs: list = field(default_factory=list)  # sub-case ids still to read (read_subcases)
    pulse: list = field(default_factory=list)        # Pulse posts: {author, date, text, replies}
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
_PANEL_JS = r"""
const p = [...document.querySelectorAll('[role=tabpanel]')].find(e => e.offsetWidth || e.offsetHeight);
if (!arguments[0]) return p || null;
if (!p) return null;
const t = p.innerText || '';
// cheap fingerprint of the panel: length + a sample, and whether Pega still shows a busy indicator
return [t.length, t.slice(0, 200) + t.slice(-200),
        /Loading/.test(t) || !!document.querySelector('.pega_ui_busyIndicator:not([style*="none"]), .loading-indicator')];
"""


def _visible_panel(b: SaltoBrowser):
    """The case tab panel on screen (one in-page call instead of asking Firefox about each panel)."""
    try:
        return b.driver.execute_script(_PANEL_JS, False)
    except WebDriverException:
        return None


def _wait_stable(b, timeout=20):
    """Wait until the visible tab panel has content that stopped changing (checked every 0.3 s)."""
    deadline, last = time.time() + timeout, None
    while time.time() < deadline:
        time.sleep(0.3)
        try:
            sig = b.driver.execute_script(_PANEL_JS, True)
        except WebDriverException:
            sig = None
        if sig and sig[0] and not sig[2] and sig[:2] == (last or [None, None])[:2]:
            return _visible_panel(b)
        last = sig
    return _visible_panel(b)


def open_tab(b: SaltoBrowser, name: str):
    tab = b.driver.find_element(By.XPATH, f"//*[@role='tab' and normalize-space(.)='{name}']")
    if tab.get_attribute("aria-selected") != "true":
        b.click(tab)
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


_NOISE = re.compile(r"^((enter|click) to (sort|filter)|no items|no cases|actions?|add|edit|refresh|search|close|save|"
                    r"submit|cancel|next|previous|first page|last page|page|of|\d{1,3}|\(\d+\)|items? per page|select|"
                    r"show more|show less|view|expand|collapse|filter|sort|go|ok|delete|advanced|showing|newest|"
                    r"oldest|on top|loading\.*|<<|<|>|>>|[-:|*]|page\s+of\s+\d+|show:.*|show sub-?cases?.*|"
                    r"show sub-case attachments)$", re.I)
_INITIALS = re.compile(r"^[A-Z]{1,3}$")  # avatar initials ("JC")


def other_lines(td: TabData):
    """What SALTO shows on the tab that is not already in its fields or tables (unusual layouts: Services...)."""
    norm = lambda s: re.sub(r"\s+", " ", str(s or "")).strip().lower()
    parts = [td.name]
    for sec, fs in td.sections:
        parts += [sec] + [x for f in fs for x in f]
    for g in td.grids:
        parts += [g.name, *g.headers] + [v for r in g.rows for v in r.values()]
    known = " ¦ ".join(norm(x) for x in parts)
    out = []
    for line in dict.fromkeys(l.strip() for l in (td.text or "").splitlines()):
        n = norm(line)
        if len(n) < 2 or _NOISE.match(n) or _INITIALS.match(line) or n in known:
            continue
        if ":" in n and all(p.strip() in known for p in n.split(":", 1) if p.strip()):
            continue
        out.append(line)
    return out


def tab_names(b):
    return [re.sub(r"\s+", " ", t.text).strip() for t in b.driver.find_elements(By.XPATH, "//*[@role='tab']")
            if t.is_displayed() and t.text.strip()]


def enter_case(b, case_id, timeout=40):
    """Switch the driver into the frame showing this case.

    Matched on the frame's own title ('Order And Deliver EQP-198834'): the case id as text is not
    enough, because a parent case lists its sub-cases' ids in its Overview tree."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for i, _ in enumerate(b.frames()):
            if i == 0:
                continue  # the portal page itself can carry the same title; the case lives in a frame
            with suppress(WebDriverException):
                title = b.driver.execute_script("return document.title || ''")
                if title.endswith(case_id) and b.driver.execute_script(
                        "return !!document.body && document.body.innerText.indexOf(arguments[0]) >= 0", f"({case_id})"):
                    return
        time.sleep(0.4)
    b.frame_with_text(f"({case_id})", timeout=5)  # last resort: the old text match


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


_PULSE_JS = r"""
const box = document.querySelector('[data-node-id=pyDisplayContextPosts]');
if (!box) return [];
const DATE = /^\d{1,2} [A-Z][a-z]{2} \d{4}( \d{1,2}:\d{2}( [AP]M)?)?$/;
const NOISE = /^(Comment|Like|Unlike|Reply|Delete|Edit|Refresh|Message|Pulse|[A-Z]{1,3}|\d+ (likes?|comments?))$/;
const out = [];
for (const p of box.querySelectorAll('.pulse-display-post')) {
  // the post's own block: climb until it holds the author + date line
  let c = p, lines = [];
  for (let i = 0; i < 8 && c.parentElement; i++) {
    c = c.parentElement;
    lines = (c.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    if (lines.some(l => DATE.test(l))) break;
  }
  const text = (p.innerText || '').trim();
  const di = lines.findIndex(l => DATE.test(l));
  const before = lines.slice(0, Math.max(di, 0)).filter(l => !NOISE.test(l));
  const author = before.length ? before[before.length - 1] : '';
  // replies: other posts nested in this block after the main text
  const replies = [...c.querySelectorAll('.pulse-display-post')].filter(x => x !== p).map(x => (x.innerText || '').trim());
  out.push({author: author, date: di >= 0 ? lines[di] : '', text: text, replies: replies, _nested: !!p.parentElement.closest('.pulse-display-post')});
}
// a reply also appears as its own post: keep top-level posts only
return out.filter((o, i, all) => !all.some((x, j) => j !== i && x.replies.includes(o.text) && x.text !== o.text));
"""


def read_pulse(b):
    """The case's Pulse feed (messages and their replies), newest first as SALTO shows it."""
    with suppress(WebDriverException):
        return [{k: v for k, v in p.items() if not k.startswith("_")}
                for p in b.driver.execute_script(_PULSE_JS) or []]
    return []


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
    for i, row in enumerate(rows):
        row["_index"], row["_case"], row["Saved as"] = i, case_id, ""
    if opts.downloads and opts.folder and rows:
        _download_rows(b, case_id, rows, opts.folder, log)
    return TabData("Attachments", grids=[Grid("Attachments", ["Title", "Category", "Added by", "Date", "Case"], rows)]
                   if rows else [], text=panel.text if panel else ""), rows


def _download_rows(b, case_id, rows, folder, log):
    """Download these attachment rows of the case currently open (Attachments tab)."""
    dest = files.sub(folder, "Downloads", case_id)
    for n, row in enumerate(rows, 1):
        log(f"Downloading {case_id} {n}/{len(rows)}: {(row['Title'] or row.get('Category', ''))[:50]}")
        try:
            row["Saved as"] = _download_one(b, case_id, row["_index"], row, dest)
        except (WebDriverException, OSError) as exc:
            row["Saved as"] = f"failed: {errors.note(exc)}"
            with suppress(WebDriverException):
                _back_to_case(b, case_id)


def download_attachments(b, main_id, rows, folder, log=print):
    """Download chosen attachment rows (from any case of the order) after the dissect.
    Opens each case in SALTO again, the main case directly and sub-cases from its Overview tree."""
    by_case = {}
    for r in rows:
        by_case.setdefault(r["_case"], []).append(r)
    for cid, items in by_case.items():
        try:
            if cid == main_id:
                if not _focus_case_tab(b, main_id):
                    raise NoSuchElementException(f"{main_id} is not open in SALTO any more: open the order again")
                enter_case(b, main_id)
            else:
                _focus_case_tab(b, main_id)
                open_subcase(b, main_id, cid)
            open_tab(b, "Attachments")
            _download_rows(b, cid, items, folder, log)
        except WebDriverException as exc:
            for r in items:
                r["Saved as"] = r["Saved as"] or f"failed: {errors.note(exc)}"
        finally:
            if cid != main_id:
                with suppress(WebDriverException):
                    close_case_tab(b, cid)
    with suppress(WebDriverException):
        _focus_case_tab(b, main_id)
    return rows


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
    more = any(x.is_displayed() for x in panel.find_elements(By.XPATH, ".//button[@title='Next Page']"))
    if max_pages <= 1:  # quick read: latest page only
        name = "History (latest page - older pages not read)" if more else "History"
        return TabData("Audit", grids=[Grid(name, g["headers"], rows)], text=raw.get("text", ""))
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


_PAGERS_JS = r"""
const root = arguments[0] || document;
return [...root.querySelectorAll('input[name=pyGridActivePage]')].filter(e => e.offsetWidth).map(e => {
  const m = (e.getAttribute('aria-label') || '').match(/Page\s+(\d+)\s+of\s+(\d+)/i);
  return m ? [+m[1], +m[2]] : [1, 1];
});
"""


def _go_page(b, index, page):
    """Type a page number into a SALTO table's page box (its onchange runs SALTO's own paginator)."""
    boxes = [e for e in b.driver.find_elements(By.XPATH, "//*[@role='tabpanel']//input[@name='pyGridActivePage']")
             if e.is_displayed()]
    if index < len(boxes):
        b.driver.execute_script("arguments[0].value = arguments[1];"
                                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                                boxes[index], str(page))
        # the table is redrawn with a new page box: wait until it says this page, then until it settles
        deadline = time.time() + 25
        while time.time() < deadline:
            with suppress(WebDriverException):
                now = [e.get_attribute("aria-label") or "" for e in b.driver.find_elements(
                    By.XPATH, "//*[@role='tabpanel']//input[@name='pyGridActivePage']") if e.is_displayed()]
                if index < len(now) and re.match(rf"Page\s+{page}\s+of", now[index], re.I):
                    break
            time.sleep(0.4)
        time.sleep(0.8)
        return _wait_stable(b)
    return None


def paged_extract(b, panel, log=print, max_pages=40):
    """extract() plus the other pages of every paged table in the panel (SALTO shows 50 rows a page)."""
    raw = extract(b, panel)
    pagers = b.driver.execute_script(_PAGERS_JS, panel) or []
    for i, (_, total) in enumerate(pagers):
        if total <= 1:
            continue
        for page in range(2, min(total, max_pages) + 1):
            log(f"  table page {page} of {total}...")
            p = _go_page(b, i, page)
            more = extract(b, p)
            for g in more.get("grids", []):
                same = next((x for x in raw.get("grids", []) if x["headers"] == g["headers"]
                             and x["name"] == g["name"]), None)
                if same is None:  # a table that only shows on this page (e.g. EQUIPMENT INFORMATION)
                    raw.setdefault("grids", []).append(g)
                    continue
                seen = {json.dumps(r, sort_keys=True) for r in same["rows"]}
                same["rows"] += [r for r in g["rows"] if json.dumps(r, sort_keys=True) not in seen]
        with suppress(WebDriverException):
            _go_page(b, i, 1)  # leave SALTO on page 1
    return raw


def _device_grid(b):
    raw = paged_extract(b, _visible_panel(b), log=lambda m: None)
    counts = [tuple(f) for s in raw.get("sections", []) for f in s["fields"] if f[0].startswith("Number of")]
    grids = [g for g in raw.get("grids", []) if "USID" in g["headers"] or "Name" in g["headers"]]
    g = grids[0] if grids else {"headers": [], "rows": []}
    _device_grid.extra = [x for x in raw.get("grids", []) if x is not g]
    return counts, g


def _set_scope(b, on):
    lab, cb = _scope_checkbox(b)
    if cb.is_selected() != on:
        b.click(lab)
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
        b.click(target)
        _wait_stable(b)
        all_g, scope_g, counts = {"headers": [], "rows": []}, {"headers": [], "rows": []}, []
        extra = []
        try:
            _, cb = _scope_checkbox(b)
            was = cb.is_selected()
            _set_scope(b, False)
            counts, all_g = _device_grid(b)
            extra = list(_device_grid.extra)  # tables shown with all devices (the scope view may hide them)
            _set_scope(b, True)
            counts2, scope_g = _device_grid(b)
            counts = counts2 or counts
            _set_scope(b, was)  # leave SALTO as we found it
        except NoSuchElementException:
            counts, all_g = _device_grid(b)
        result.append(ScopeNode(n["product"], n["node"], counts,
                                Grid("Scope of work devices", scope_g["headers"], scope_g["rows"]),
                                Grid("All devices", all_g["headers"], all_g["rows"]),
                                [Grid(x["name"], x["headers"], x["rows"])
                                 for x in extra + [y for y in getattr(_device_grid, "extra", []) if y not in extra]]))
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
    b.click(link[0])
    time.sleep(1)
    if "already open" in _accept_alert(b).lower() and _focus_case_tab(b, sub_id):
        enter_case(b, sub_id, timeout=60)  # open in a tab SALTO did not name after the case
        return
    try:
        enter_case(b, sub_id, timeout=90)  # a busy SALTO can take more than a minute to open a sub-case
    except NoSuchElementException:
        # SALTO sometimes fails to load it ("Problem loading page" in a "Work Item" tab): close that, ask again
        if not _close_broken_tabs(b) and _focus_case_tab(b, sub_id):
            enter_case(b, sub_id, timeout=60)
            return
        _focus_case_tab(b, parent_id)
        enter_case(b, parent_id)
        open_tab(b, "Overview")
        link = [a for a in b.driver.find_elements(
            By.XPATH, f"//*[@role='tabpanel']//a[contains(normalize-space(.), '({sub_id})')]") if a.is_displayed()]
        if not link:
            raise
        b.click(link[0])
        enter_case(b, sub_id, timeout=90)
    time.sleep(0.5)


def _close_broken_tabs(b):
    """Close SALTO tabs whose page failed to load (Firefox 'Problem loading page'). True if one was closed."""
    d = b.driver
    closed = False
    d.switch_to.default_content()
    for li in d.find_elements(By.XPATH, "//li[@role='tab']"):
        with suppress(WebDriverException):
            if not li.is_displayed() or not (li.get_attribute("aria-label") or "").startswith("Work Item"):
                continue
            d.execute_script("arguments[0].click()", li)
            time.sleep(1.5)
            broken = False
            for _ in b.frames():
                if d.execute_script("return document.title") == "Problem loading page":
                    broken = True
                    break
            d.switch_to.default_content()
            if broken:
                for x in li.find_elements(By.XPATH, ".//span[contains(@class,'iconCloseSmall')]"):
                    d.execute_script("arguments[0].click()", x)
                    time.sleep(1.5)
                    closed = True
    return closed


def close_case_tab(b, case_id):
    d = b.driver
    d.switch_to.default_content()
    tabs = d.find_elements(By.XPATH, f"//li[@role='tab' and starts-with(@aria-label, '{case_id} ')]") or \
        d.find_elements(By.XPATH, "//li[@role='tab' and starts-with(@aria-label, 'Work Item') and @aria-selected='true']")
    for li in tabs:
        for x in li.find_elements(By.XPATH, ".//span[contains(@class,'iconCloseSmall')]"):
            d.execute_script("arguments[0].click()", x)
            time.sleep(1.5)
            _accept_alert(b)
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
    data.pulse = read_pulse(b)
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
                data.tabs[name] = read_audit(b, log, max_pages=60 if opts.full_audit else 1)
            elif name in ("TS", "Site") and depth > 0:
                continue  # a sub-case repeats the order's device tree and site: read once, on the main case
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
                    td.grids += [Grid(f"{n.node} - {g.name}", g.headers, g.rows) for g in getattr(n, "extra", [])]
                data.tabs[name] = td
            else:
                panel = open_tab(b, name)
                raw = paged_extract(b, panel, log)
                td = _tabdata(name, raw)
                for sub in [s for s in raw.get("subtabs", []) if s not in names]:   # tabs inside a tab
                    with suppress(WebDriverException):
                        sp = open_tab(b, sub)
                        st = _tabdata(sub, paged_extract(b, sp, log))
                        td.sections += [(f"{sub} / {s}", f) for s, f in st.sections]
                        td.grids += [Grid(f"{sub} / {g.name}", g.headers, g.rows) for g in st.grids]
                        td.text += f"\n{sub}\n{st.text}"
                    open_tab(b, name)
                data.tabs[name] = td
            if opts.tab_screenshots and opts.folder:
                from . import capture
                shot = capture.screenshot_screen(b, files.sub(opts.folder, "Screenshots"), f"{case_id}_{name}")
                data.screenshots.append(shot)
                enter_case(b, case_id)
        except (WebDriverException, IndexError) as exc:
            if errors.browser_gone(exc):
                raise  # every other tab would fail the same way
            msg = f"{case_id} / {name}: {errors.note(exc)}"
            log("  could not read " + msg)
            data.errors.append(msg)
            with suppress(WebDriverException):
                enter_case(b, case_id, timeout=15)

    if opts.flip and case_id.startswith("EQP-"):  # equipment: serial numbers from FLIP
        from . import flip
        try:
            data.flip = flip.read_eqp(b, case_id, opts.folder, log)
            data.errors += data.flip.get("errors", [])
        except Exception as exc:  # FLIP trouble never stops the rest of the order
            data.errors.append(f"{case_id} / FLIP: {errors.note(exc)}")
            with suppress(WebDriverException):
                enter_case(b, case_id, timeout=15)

    if opts.subcases and depth == 0:
        # EQPs first: their FLIP serial numbers are usually what people wait for
        data.pending_subs = sorted(sub_ids, key=lambda s: not s.startswith("EQP-"))
        if not opts.later_subcases:
            read_subcases(b, data, opts, log, read_stages)
    with suppress(WebDriverException):
        enter_case(b, case_id, timeout=15)
        open_tab(b, "Overview")
    return data


def read_subcases(b, data, opts, log=print, read_stages=None, on_each=None):
    """Read data.pending_subs one by one (each opened from the main case); on_each(sub) after each one."""
    case_id = data.stc_id
    total = len(data.pending_subs) + len(data.subcases)
    failed = {}  # sub-case -> first error: tried once more at the end (SALTO is often just slow)
    while data.pending_subs:
        if opts.cancel is not None and opts.cancel.is_set():
            log("Stopped reading sub-cases (another order was opened).")
            break
        sid = data.pending_subs[0]
        log(f"Sub-case {len(data.subcases) + 1}/{total}: {sid}...")
        sub = None
        try:
            open_subcase(b, case_id, sid)
            sub = read_case(b, sid, opts, log, read_stages, depth=1)
            data.subcases.append(sub)
        except Exception as exc:  # one bad sub-case never stops the others
            if errors.browser_gone(exc):  # ...but without Firefox none of them can be read
                data.errors.append(f"{sid}: {errors.note(exc)}")
                log("Firefox was closed: stopped reading sub-cases. Open the order again to read the rest.")
                break
            if sid in failed:
                data.errors.append(f"{sid}: {failed[sid]}")
                log(f"  could not open {sid}")
            else:
                failed[sid] = errors.note(exc)
                data.pending_subs.append(sid)  # second try after the others
                log(f"  {sid} is slow to open; trying it again at the end")
        finally:
            data.pending_subs.pop(0)
            with suppress(WebDriverException):
                close_case_tab(b, sid)
            with suppress(WebDriverException):
                _focus_case_tab(b, case_id)
                enter_case(b, case_id)
        if on_each and sub:
            on_each(sub)
    return data


def _focus_case_tab(b, case_id):
    d = b.driver
    d.switch_to.default_content()
    for li in d.find_elements(By.XPATH, f"//li[@role='tab' and starts-with(@aria-label, '{case_id} ')]"):
        if li.get_attribute("aria-selected") != "true":
            b.click(li)
            time.sleep(0.8)
        return True
    # SALTO sometimes labels a case's tab "Work Item": look inside those tabs
    for li in d.find_elements(By.XPATH, "//li[@role='tab' and starts-with(@aria-label, 'Work Item')]"):
        with suppress(WebDriverException):
            if not li.is_displayed():
                continue
            d.execute_script("arguments[0].click()", li)
            time.sleep(1.5)
            for i, _ in enumerate(b.frames()):
                if i and (d.execute_script("return document.title || ''") or "").endswith(case_id):
                    d.switch_to.default_content()
                    return True
            d.switch_to.default_content()
    return False


def _accept_alert(b):
    """Close a browser alert (e.g. SALTO's 'Work Object Already Open'); returns its text, or ''."""
    with suppress(WebDriverException):
        alert = b.driver.switch_to.alert
        text = alert.text
        alert.accept()
        return text
    return ""
