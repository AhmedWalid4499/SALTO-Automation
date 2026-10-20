"""Screenshots of SALTO: the whole Firefox view, or one element the user clicks on."""
import time
from contextlib import suppress

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

from . import files

# Installed in every frame: orange outline follows the mouse; a click marks the element
# (instead of acting on it) and Esc cancels.
_PICKER_JS = r"""
if (window.__sbPicker) return;
const st = document.createElement('style');
st.id = '__sbPickStyle';
st.textContent = '.__sbHover{outline:3px solid #FF7900 !important; outline-offset:-1px; cursor:crosshair !important}';
(document.head || document.documentElement).appendChild(st);
let cur = null;
const over = e => { if (cur) cur.classList.remove('__sbHover'); cur = e.target; cur.classList.add('__sbHover'); };
const click = e => {
  e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
  if (cur) cur.classList.remove('__sbHover');
  e.target.setAttribute('data-sb-pick', '1');
  window.top.__sbDone = 'picked';
};
const key = e => { if (e.key === 'Escape') window.top.__sbDone = 'cancel'; };
document.addEventListener('mouseover', over, true);
document.addEventListener('click', click, true);
const down = ev => { ev.preventDefault(); ev.stopPropagation(); };
document.addEventListener('mousedown', down, true);
document.addEventListener('keydown', key, true);
window.__sbPicker = {over, click, key, down};
"""

_UNPICK_JS = r"""
const p = window.__sbPicker;
if (p) {
  document.removeEventListener('mouseover', p.over, true);
  document.removeEventListener('click', p.click, true);
  document.removeEventListener('keydown', p.key, true);
  document.removeEventListener('mousedown', p.down, true);
  delete window.__sbPicker;
}
document.querySelectorAll('.__sbHover').forEach(e => e.classList.remove('__sbHover'));
const s = document.getElementById('__sbPickStyle'); if (s) s.remove();
"""


def current_label(b):
    """Name for the screenshot: the open SALTO tab (and the case tab inside it)."""
    d = b.driver
    label = "SALTO"
    with suppress(WebDriverException):
        d.switch_to.default_content()
        sel = [t for t in d.find_elements(By.XPATH, "//li[@role='tab' and @aria-selected='true']") if t.is_displayed()]
        if sel:
            label = (sel[0].get_attribute("aria-label") or sel[0].text).split(" Press")[0].strip() or label
        for _ in b.frames():
            inner = [t for t in d.find_elements(By.XPATH, "//*[@role='tab' and @aria-selected='true']")
                     if t.is_displayed() and t.text.strip()]
            if inner and inner[0].text.strip() != label:
                label = f"{label}_{inner[0].text.strip()}"
                break
        d.switch_to.default_content()
    return label


def screenshot_screen(b, folder):
    """Save what Firefox shows now as <Tab>_<n>.png in folder."""
    path = files.numbered(folder, current_label(b))
    b.driver.switch_to.default_content()
    b.driver.save_screenshot(path)
    return path


def _bring_to_front(b):
    with suppress(WebDriverException):
        b.driver.minimize_window()
        b.driver.maximize_window()


def pick_and_capture(b, folder, timeout=180, log=print):
    """Let the user click an element in SALTO; save that element as a PNG. Returns the path or None."""
    d = b.driver
    _bring_to_front(b)
    for _ in b.frames():
        with suppress(WebDriverException):
            d.execute_script(_PICKER_JS)
    d.switch_to.default_content()
    d.execute_script("window.__sbDone = null")
    log("Click on what you want to capture in the Firefox window (Esc to cancel)...")
    deadline = time.time() + timeout
    result = None
    try:
        while time.time() < deadline:
            d.switch_to.default_content()
            done = d.execute_script("return window.__sbDone")
            if done == "cancel":
                log("Capture cancelled.")
                return None
            if done == "picked":
                break
            time.sleep(0.4)
        else:
            log("Capture timed out.")
            return None
        label = current_label(b)
        for _ in b.frames():
            els = d.find_elements(By.CSS_SELECTOR, "[data-sb-pick]")
            if els:
                el = els[0]
                d.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                time.sleep(0.3)
                path = files.numbered(folder, f"{label}_selection")
                el.screenshot(path)
                d.execute_script("arguments[0].removeAttribute('data-sb-pick')", el)
                result = path
                break
    finally:
        for _ in b.frames():
            with suppress(WebDriverException):
                d.execute_script(_UNPICK_JS)
                d.execute_script("document.querySelectorAll('[data-sb-pick]').forEach(e => e.removeAttribute('data-sb-pick'))")
        d.switch_to.default_content()
    return result
