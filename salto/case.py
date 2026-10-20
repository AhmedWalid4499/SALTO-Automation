"""Reading an open STC case: every tab, participants and the TS scope of work.

All functions expect the driver to be switched into the case's frame
(actions.open_case leaves it there).
"""
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field

from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By

from .browser import SaltoBrowser

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract.js"), encoding="utf-8") as _f:
    EXTRACT_JS = _f.read()

CASE_TABS = ["Overview", "TS", "Commercial Content", "Site", "Information", "Attachments", "Audit", "Event"]


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
    devices: Grid


@dataclass
class Participant:
    name: str
    role: str
    party: str  # Pega party key, e.g. TechnicalDesignTeam


@dataclass
class CaseData:
    stc_id: str = ""
    title: str = ""
    header: list = field(default_factory=list)       # [(label, value)] case header fields
    participants: list = field(default_factory=list)
    scope: list = field(default_factory=list)        # [ScopeNode]
    tabs: dict = field(default_factory=dict)         # tab name -> TabData
    errors: list = field(default_factory=list)

    @property
    def scope_devices(self):
        out = []
        for n in self.scope:
            out.extend(n.devices.rows)
        return out


# ---------------------------------------------------------------- helpers
def _visible_panel(b: SaltoBrowser):
    for p in b.driver.find_elements(By.XPATH, "//*[@role='tabpanel']"):
        with suppress(WebDriverException):
            if p.is_displayed():
                return p
    return None


def open_tab(b: SaltoBrowser, name: str):
    tab = b.driver.find_element(By.XPATH, f"//*[@role='tab' and normalize-space(.)='{name}']")
    if tab.get_attribute("aria-selected") != "true":
        tab.click()
    deadline = time.time() + 20
    last = None
    while time.time() < deadline:  # wait for the panel to load and settle
        time.sleep(0.8)
        p = _visible_panel(b)
        txt = p.text if p else ""
        if txt and txt == last and "Loading" not in txt:
            return p
        last = txt
    return _visible_panel(b)


def extract(b: SaltoBrowser, root=None) -> dict:
    return b.driver.execute_script(EXTRACT_JS, root) or {}


def _tabdata(name, raw) -> TabData:
    return TabData(
        name=name,
        sections=[(s["name"], [tuple(f) for f in s["fields"]]) for s in raw.get("sections", [])],
        grids=[Grid(g["name"], g["headers"], g["rows"]) for g in raw.get("grids", [])],
        text=raw.get("text", ""),
    )


# ---------------------------------------------------------------- header
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


# ---------------------------------------------------------------- participants
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
  const o = {Name: name, Level: Math.max(0, Math.round((pad - 36) / 18))};
  const tr = right[i];
  if (tr) [...tr.querySelectorAll(':scope > td')].forEach((td, j) => {
    const h = heads[j]; if (h && h !== 'Name') o[h] = clean(td.textContent);
  });
  return o;
});
"""


def read_overview(b) -> TabData:
    panel = open_tab(b, "Overview")
    rows = b.driver.execute_script(_OVERVIEW_JS, panel) or []
    headers = ["Name", "Assigned To", "Deadline/Completion date", "Urgency", "Status"]
    for r in rows:
        r["Name"] = "    " * int(r.pop("Level", 0)) + r["Name"]
        for h in r:
            if h not in headers:
                headers.append(h)
    return TabData("Overview", grids=[Grid("Cases & assignments", headers, rows)], text=panel.text if panel else "")


# ---------------------------------------------------------------- attachments
_ATTACH_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const panel = arguments[0] || document;
return [...panel.querySelectorAll('[base_ref*="pyAttachments("]')].map(td => {
  const lines = (td.innerText || '').split('\n').map(clean).filter(Boolean);
  const meta = lines.find(l => (l.match(/\|/g) || []).length >= 2) || '';
  const parts = meta.split('|').map(clean);
  const a = td.querySelector('a.Case_tools');
  const title = clean(a && a.getAttribute('title')) || lines.filter(l => l !== meta).join(' ');
  return {Title: title, Case: parts[0] || '', Category: parts[1] || '', 'Added by': parts[2] || '', Date: parts[3] || ''};
});
"""


def read_attachments(b) -> TabData:
    panel = open_tab(b, "Attachments")
    rows = b.driver.execute_script(_ATTACH_JS, panel) or []
    return TabData("Attachments", grids=[Grid("Attachments", ["Title", "Case", "Category", "Added by", "Date"], rows)],
                   text=panel.text if panel else "")


# ---------------------------------------------------------------- TS scope of work
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


def _wait_stable(b, timeout=20):
    deadline, last = time.time() + timeout, None
    while time.time() < deadline:
        time.sleep(0.8)
        p = _visible_panel(b)
        txt = p.text if p else ""
        if txt == last:
            return p
        last = txt
    return _visible_panel(b)


def read_ts_scope(b, log=print):
    """For every product node in the TS tree: click it, tick 'Scope of work only', read devices."""
    panel = open_tab(b, "TS")
    nodes = b.driver.execute_script(_TS_NODES_JS, panel) or []
    result = []
    for n in nodes:
        log(f"TS: {n['product']} > {n['node']} (scope of work only)...")
        el = b.driver.find_elements(By.XPATH, "//*[@role='tabpanel']//ul[contains(@class,'rowContent')]")
        el = [e for e in el if e.is_displayed()][n["index"]]
        target = el.find_elements(By.XPATH, ".//div[contains(@class,'oflowDiv')]")
        target = target[-1] if target else el
        b.driver.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
        target.click()
        _wait_stable(b)
        try:
            lab, cb = _scope_checkbox(b)
            if not cb.is_selected():
                lab.click()
                _wait_stable(b)
        except NoSuchElementException:
            log("  'Scope of work only' not found for this node.")
        raw = extract(b, _visible_panel(b))
        counts = [f for s in raw.get("sections", []) for f in s["fields"] if f[0].startswith("Number of")]
        grids = [g for g in raw.get("grids", []) if "USID" in g["headers"] or "Name" in g["headers"]]
        g = grids[0] if grids else {"name": "", "headers": [], "rows": []}
        result.append(ScopeNode(n["product"], n["node"], [tuple(c) for c in counts],
                                Grid("Scope of work devices", g["headers"], g["rows"])))
    return result


# ---------------------------------------------------------------- everything
def read_case(b: SaltoBrowser, stc_id: str, log=print) -> CaseData:
    data = CaseData(stc_id=stc_id, title=b.driver.title)
    data.header = read_header(b)
    data.participants = read_participants(b)
    names = tab_names(b) or CASE_TABS
    for name in names:
        log(f"Reading tab: {name}...")
        try:
            if name == "Overview":
                data.tabs[name] = read_overview(b)
            elif name == "Attachments":
                data.tabs[name] = read_attachments(b)
            elif name == "TS":
                data.scope = read_ts_scope(b, log)
                td = TabData("TS")
                for n in data.scope:
                    td.sections.append((f"{n.product} > {n.node}", n.counts))
                    td.grids.append(Grid(f"{n.node} - Scope of work devices", n.devices.headers, n.devices.rows))
                data.tabs[name] = td
            else:
                panel = open_tab(b, name)
                raw = extract(b, panel)
                td = _tabdata(name, raw)
                # tabs nested inside this tab: read each one too
                for sub in [s for s in raw.get("subtabs", []) if s not in names]:
                    with suppress(WebDriverException):
                        sp = open_tab(b, sub)
                        st = _tabdata(sub, extract(b, sp))
                        td.sections += [(f"{sub} / {s}", f) for s, f in st.sections]
                        td.grids += [Grid(f"{sub} / {g.name}", g.headers, g.rows) for g in st.grids]
                    open_tab(b, name)
                data.tabs[name] = td
        except (WebDriverException, IndexError) as exc:
            msg = f"{name}: {str(exc).splitlines()[0]}"
            log("  could not read " + msg)
            data.errors.append(msg)
    open_tab(b, "Overview")
    return data


def tab_names(b):
    return [re.sub(r"\s+", " ", t.text).strip() for t in b.driver.find_elements(By.XPATH, "//*[@role='tab']") if t.is_displayed()]
