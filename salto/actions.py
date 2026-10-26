"""SALTO page actions: STC search, opening a case, reading stage and EQPs."""
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field

from selenium.common.exceptions import (NoSuchElementException,
                                        StaleElementReferenceException,
                                        WebDriverException)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from . import case as case_reader
from .browser import _MASK_JS, SaltoBrowser

STC_ID_RE = re.compile(r"^[A-Z]{2,8}-\d{4,}$")
EQP_RE = re.compile(r"\((EQP-\d+)\)")


@dataclass
class SearchRow:
    stc_id: str
    sub_case_id: str
    cells: list


@dataclass
class Stage:
    name: str
    state: str  # "completed" | "current" | "pending"


@dataclass
class OrderReport:
    order_ref: str
    rows: list = field(default_factory=list)
    stc_id: str = ""
    stages: list = field(default_factory=list)
    current_stage: str = ""
    status: str = ""
    eqps: list = field(default_factory=list)
    folder: str = ""     # <base>/<order> - <STC>
    case: object = None  # case_reader.CaseData when the full read ran
    org: dict = field(default_factory=dict)  # participant name -> Org Chart entry (email, manager...)


# ---------------------------------------------------------------------- search
def open_stc_search(b: SaltoBrowser):
    b.log("Opening STC Search...")
    item_xp = "//*[(@role='menuitem' or self::a or self::span) and normalize-space(.)='STC Search']"
    toggle_xp = "//*[@title='Toggle Left Navigation' or @aria-label='Toggle Left Navigation']"
    b.driver.switch_to.default_content()
    # Already open as a SALTO tab: just select it (the menu would ask "reopen and lose changes?")
    open_tab = [t for t in b.driver.find_elements(By.XPATH, "//li[@role='tab' and starts-with(@aria-label, 'STC Search')]")
                if t.is_displayed()]
    if open_tab:
        b.click(open_tab[0])
        b.find_visible("//label[contains(normalize-space(.), 'Commercial Order Ref')]", timeout=30)
        return
    # On wide windows SALTO pins the menu open and hides the toggle; on narrow ones it is collapsed
    if not any(e.is_displayed() for e in b.driver.find_elements(By.XPATH, item_xp)):
        for t in b.driver.find_elements(By.XPATH, toggle_xp):
            if t.is_displayed():
                b.click(t)
                time.sleep(1)
                break
    b.click(b.find_visible(item_xp))
    # The search form lives in its own frame
    b.find_visible("//label[contains(normalize-space(.), 'Commercial Order Ref')]", timeout=30)


def _order_ref_input(b: SaltoBrowser):
    label = b.find_visible("//label[contains(normalize-space(.), 'Commercial Order Ref')]")
    target = label.get_attribute("for")
    if target:
        return b.driver.find_element(By.ID, target)
    return label.find_element(By.XPATH, "following::input[1]")


def search_order(b: SaltoBrowser, order_ref: str):
    open_stc_search(b)
    field_ = _order_ref_input(b)
    field_.clear()
    field_.send_keys(order_ref)
    b.log(f"Searching for {order_ref}...")
    field_.send_keys(Keys.ENTER)
    rows = _wait_rows(b, order_ref, timeout=8)
    if not rows:  # Enter didn't trigger the search on this form: use the button
        with suppress(NoSuchElementException):
            b.click(b.driver.find_element(By.XPATH, "//button[normalize-space(.)='Search']"))
        rows = _wait_rows(b, order_ref, timeout=40)
    b.log(f"{len(rows)} result row(s).")
    return rows


def _read_rows(b: SaltoBrowser):
    rows = []
    for tr in b.driver.find_elements(By.XPATH, "//tr[td]"):
        with suppress(StaleElementReferenceException):
            cells = [td.text.strip() for td in tr.find_elements(By.XPATH, "./td")]
            ids = [c for c in cells if STC_ID_RE.match(c)]
            if ids:
                sub = ids[1] if len(ids) > 1 else ""
                rows.append(SearchRow(ids[0], sub, cells))
    return rows


def _wait_rows(b: SaltoBrowser, order_ref, timeout):
    """Wait for result rows belonging to this order (ignores a previous search's grid)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = [r for r in _read_rows(b) if order_ref in r.cells]
        if rows:
            return rows
        time.sleep(0.7)
    return []


# ---------------------------------------------------------------------- case
def open_case(b: SaltoBrowser, stc_id: str):
    """Double-click the first result cell with this STC ID (a single click only selects the row)."""
    b.log(f"Opening {stc_id}...")
    for attempt, wait in enumerate((45, 90)):
        if attempt:
            b.log(f"SALTO is slow to open {stc_id}; trying again...")
            try:  # it may have opened meanwhile, the results no longer on screen
                b.frame_with_text(f"({stc_id})", "Overview", timeout=3)
                break
            except NoSuchElementException:
                pass
        b.driver.switch_to.default_content()
        try:
            cell = b.find_visible(f"//td[normalize-space(.)='{stc_id}']")
        except NoSuchElementException:
            if not attempt:
                raise
            # the results are gone: SALTO is opening the case (slowly), so wait for it rather than click again
            b.frame_with_text(f"({stc_id})", "Overview", timeout=wait)
            break
        # Results are often below the fold; the mouse can only act inside the viewport
        b.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell)
        deadline = time.time() + 30
        while time.time() < deadline and b.driver.execute_script(_MASK_JS):  # SALTO still busy: clicks are lost
            time.sleep(0.3)
        time.sleep(0.5)
        try:
            ActionChains(b.driver).move_to_element(cell).double_click(cell).perform()
        except WebDriverException:
            b.driver.execute_script(
                "const t = arguments[0].querySelector('*') || arguments[0];"
                "['mousedown','mouseup','click','mousedown','mouseup','click','dblclick'].forEach(n =>"
                "  t.dispatchEvent(new MouseEvent(n, {bubbles: true, cancelable: true, view: window, detail: n==='dblclick'?2:1})));",
                cell)
        try:
            b.frame_with_text(f"({stc_id})", "Overview", timeout=wait)
            break
        except NoSuchElementException:
            if attempt:
                raise
    time.sleep(1.5)  # let the stage bar and overview tree render


_STAGES_JS = r"""
function bg(el){
  for (let i=0; el && i<4; i++, el=el.parentElement){
    const c = getComputedStyle(el).backgroundColor;
    const m = c.match(/\d+/g);
    if (m && !(m.length===4 && +m[3]===0) && !(+m[0]>235 && +m[1]>235 && +m[2]>235)) return m.map(Number);
  }
  return null;
}
const out = [];
const seen = new Set();
document.querySelectorAll('[class*="stage" i], [aria-current="step"]').forEach(el => {
  if (!el.offsetParent) return;
  const t = (el.innerText || '').trim();
  if (!t || t.length > 40 || t.includes('\n') || seen.has(t)) return;
  seen.add(t);
  out.push({name: t, cls: String(el.className), ariaCurrent: el.getAttribute('aria-current'), rgb: bg(el)});
});
return out;
"""


def _stage_state(info):
    cls = info.get("cls", "").lower()
    if info.get("ariaCurrent") in ("step", "true", "page") or re.search(r"current|active", cls):
        return "current"
    if re.search(r"complete|past|done", cls):
        return "completed"
    rgb = info.get("rgb")
    if rgb:
        r, g, bl = rgb[:3]
        if bl > r + 60 and bl >= g:
            return "current"   # blue chevron
        if g > r + 30 and g > bl:
            return "completed"  # green chevron
    return "pending"


def read_stages(b: SaltoBrowser):
    raw = b.driver.execute_script(_STAGES_JS) or []
    stages = [Stage(i["name"], _stage_state(i)) for i in raw]
    # keep only the stage bar entries (short labels, no field captions)
    stages = [s for s in stages if not s.name.lower().startswith(("stage", "stages"))]
    return stages


def read_status(b: SaltoBrowser):
    with suppress(NoSuchElementException):
        el = b.driver.find_element(By.XPATH, "//*[normalize-space(.)='Status']/following::*[normalize-space(.)!=''][1]")
        return el.text.strip()
    return ""


def read_eqps(b: SaltoBrowser):
    with suppress(NoSuchElementException, WebDriverException):
        tab = b.driver.find_element(By.XPATH, "//*[@role='tab' and normalize-space(.)='Overview']")
        if tab.get_attribute("aria-selected") != "true":
            b.click(tab)
            time.sleep(2)
    text = b.driver.execute_script("return document.body.textContent || ''")
    found = []
    for m in EQP_RE.findall(text):
        if m not in found:
            found.append(m)
    return found


# ---------------------------------------------------------------------- flow
def order_lookup(b: SaltoBrowser, order_ref: str, base_dir: str = "", full: bool = True,
                 opts: "case_reader.Options" = None) -> OrderReport:
    """Search the order, open its first STC and (full=True) dissect everything.

    Files (downloads, screenshots) go to <base_dir>/<order> - <STC>/.
    """
    from . import files
    b.ensure_logged_in()
    rep = OrderReport(order_ref=order_ref)
    rep.rows = search_order(b, order_ref)
    if not rep.rows:
        b.log("No STC found for this order.")
        return rep
    # an order can have a withdrawn/cancelled STC listed before the live one: open the live one
    dead = re.compile(r"withdrawn|cancel", re.I)
    live = [r for r in rep.rows if not any(dead.search(c) for c in r.cells)]
    rep.stc_id = (live or rep.rows)[0].stc_id
    others = sorted({r.stc_id for r in rep.rows} - {rep.stc_id})
    if others:
        b.log(f"Other STC(s) for this order: {', '.join(others)}")
    if base_dir:
        rep.folder = files.order_folder(base_dir, order_ref, rep.stc_id)
    open_case(b, rep.stc_id)
    rep.stages = read_stages(b)
    cur = [s.name for s in rep.stages if s.state == "current"]
    if cur:
        rep.current_stage = cur[0]
    elif rep.stages and all(s.state == "completed" for s in rep.stages):
        rep.current_stage = "Completed"  # every stage green, End included: the case is closed
    else:
        rep.current_stage = ""
    rep.status = read_status(b)
    rep.eqps = read_eqps(b)
    if full:
        opts = opts or case_reader.Options()
        opts.folder = rep.folder
        rep.case = case_reader.read_case(b, rep.stc_id, opts, log=b.log, read_stages=read_stages)
        rep.case.stages = rep.stages
        info = dict(f for _, fs in rep.case.tabs.get("Information", case_reader.TabData("")).sections for f in fs)
        rep.status = next((v for k, v in info.items() if k.endswith("Case Status") and v), rep.status)
        for sc in rep.case.subcases:  # EQPs nested deeper in the tree
            if sc.stc_id.startswith("EQP-") and sc.stc_id not in rep.eqps:
                rep.eqps.append(sc.stc_id)
    b.log(f"Done. Stage: {rep.current_stage or '?'} | EQPs: {len(rep.eqps)}"
          + (f" | sub-cases: {len(rep.case.subcases)}" if rep.case else ""))
    return rep
