"""Orange sign-in without showing Firefox: the user answers in SALTO Buddy's own windows.

prompt(kind, **data) is supplied by the app (ui.signin). It is called from the browser thread:
- "choose": {title, message, options: [(id, label, description)], remember: bool} -> (id, remember) or None
- "fields": {title, message, fields: [{key, label, secret}], error} -> {key: value} or None
- "wait":   {title, message, code} -> shows a non-blocking message (e.g. "type your PIN", a number to tap)
- "close":  closes the "wait" message
Returning None means "show me the Firefox window instead".

What the user types is typed into the sign-in page and then forgotten: never logged, never saved.
A PKI PIN is never asked here: Firefox asks for it in its own password window, which SALTO Buddy brings up
just for that moment (a hidden Firefox cannot show it).
"""
import re
import time
from contextlib import suppress
from urllib.parse import urlparse

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

METHODS = [("pki", "Orange PKI", "Your Orange PKI card or certificate. Firefox shows its password window for "
                                 "your PIN, then hides again (preferred by Orange)."),
           ("group", "Orange GroupIdentity", "Your Domain\\Orange ID, password and a second factor (code)."),
           ("microsoft", "Microsoft Professional Account", "Your Microsoft account (often automatic on an Orange "
                                                           "PC; otherwise password and phone approval).")]
BUTTONS = {"pki": "1_PKI", "group": "2_GroupIdentity", "microsoft": "4_EntraID"}
TEXTS = {"pki": "pki", "group": "groupidentity", "microsoft": "professional"}

_FIELDS_JS = r"""
const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length) &&
                 getComputedStyle(e).visibility !== 'hidden';
const out = [];
for (const el of document.querySelectorAll('input')) {
  const t = (el.type || 'text').toLowerCase();
  if (!['text', 'email', 'password', 'tel', 'number'].includes(t) || !vis(el) || el.disabled || el.readOnly) continue;
  let label = '';
  if (el.id) { const l = document.querySelector('label[for="' + el.id + '"]'); if (l) label = l.innerText; }
  label = (label || el.getAttribute('aria-label') || el.placeholder || el.name || el.id || 'Value').trim();
  out.push({el: el, label: label.replace(/\s+/g, ' ').slice(0, 60), secret: t === 'password', filled: !!el.value});
}
return out;
"""
_ERROR_JS = r"""
const vis = e => !!(e.offsetWidth || e.offsetHeight);
const sel = '[role=alert], .alert-error, .alert-danger, .error, .error-message, #usernameError, #passwordError, ' +
            '#errorText, .text-danger, .invalid-feedback';
return [...document.querySelectorAll(sel)].filter(vis).map(e => e.innerText.trim()).filter(Boolean).join(' ').slice(0, 300);
"""


class SignIn:
    def __init__(self, browser, prompt, cfg=None, log=print):
        self.b, self.prompt, self.cfg, self.log = browser, prompt, cfg if cfg is not None else {}, log
        self.method = None
        self.need_visible = False  # PKI: Firefox must be shown for its PIN window
        self.waiting = None   # message shown in a "wait" window
        self.last_form = None
        self.idle_since = None

    @property
    def d(self):
        return self.b.driver

    # ------------------------------------------------------------ one look at the current page
    def step(self):
        """Do what the current sign-in page needs. Returns False when the user asked to see Firefox."""
        host = urlparse(self.d.current_url).hostname or ""
        if self._chooser():
            return self._pick_method()
        if "microsoftonline" in host or "login.live" in host or "microsoft" in host:
            return self._microsoft()
        return self._form_or_wait()

    def done(self):
        self._wait(None)

    # ------------------------------------------------------------ Orange Connect: choose the method
    def _chooser(self):
        with suppress(Exception):
            return bool(self.d.find_elements(By.ID, BUTTONS["pki"])) or bool(
                self.d.find_elements(By.XPATH, "//*[contains(normalize-space(.), 'Select an authentication mode')]"))
        return False

    def _pick_method(self):
        method = self.method or self.cfg.get("signin_method") or ""
        if method not in BUTTONS:
            answer = self.prompt("choose", title="Sign in to SALTO",
                                 message="Orange needs you to sign in. How do you want to sign in?",
                                 options=METHODS, remember=True)
            if not answer:
                return False
            method, remember = answer
            if remember:
                self.cfg["signin_method"] = method
                getattr(self.b, "save_cfg", lambda: None)()
        self.method = method
        btn = self._button(method)
        if btn is None:
            self.log("The sign-in page has changed: opening the Firefox window...")
            return False
        if method == "pki" and self.b.headless:
            # the PIN is asked in Firefox's own password window: Firefox must be on screen for that moment
            self.need_visible = True
            return False
        self.log(f"Signing in with {dict((m[0], m[1]) for m in METHODS)[method]}...")
        with suppress(WebDriverException):
            self.d.execute_script("arguments[0].scrollIntoView({block: 'center'})", btn)
        # click without waiting for the next page: with PKI it only loads once the PIN has been typed
        with suppress(Exception):
            self.d.set_page_load_timeout(3)
        try:
            btn.click()
        except Exception:  # page-load timeout while the PIN window is open: expected
            pass
        if method == "pki":
            self._wait("Firefox is asking for your PKI PIN in its password window: type it there. Firefox goes "
                       "back out of sight as soon as you are signed in.", title="Orange PKI")
        # wait for the page to move on (PKI: while the user types the PIN in Firefox's password window)
        deadline = time.time() + (90 if method == "pki" else 20)
        while time.time() < deadline:
            time.sleep(1)
            try:
                moved = not self._chooser()
            except Exception:  # Firefox busy with its PIN window: keep waiting
                moved = False
            if moved:
                self.clicks = 0
                with suppress(Exception):
                    self.d.set_page_load_timeout(60)
                return True
        self.clicks = getattr(self, "clicks", 0) + 1
        if self.clicks >= 2:  # the page does not react: let the user finish in Firefox
            self.log("The Orange sign-in page did not react: opening the Firefox window...")
            return False
        return True

    def _button(self, method):
        with suppress(WebDriverException):
            # the page gives the same id to each method's icon and to its Connect button: take the button
            for el in self.d.find_elements(By.XPATH, f"//button[@id='{BUTTONS[method]}']"):
                if el.is_displayed():
                    return el
            for el in self.d.find_elements(By.XPATH, "//button|//a|//input[@type='submit']"):
                text = (el.text + " " + (el.get_attribute("id") or "")).lower()
                if el.is_displayed() and TEXTS[method] in text.replace(" ", ""):
                    return el
        return None

    # ------------------------------------------------------------ Microsoft pages
    def _microsoft(self):
        d = self.d
        with suppress(WebDriverException):
            # number matching: show the number to tap in the Authenticator app
            nums = [e.text.strip() for e in d.find_elements(By.ID, "idRichContext_DisplaySign") if e.is_displayed()]
            if nums and nums[0]:
                self._wait(f"Open Microsoft Authenticator on your phone and tap this number:", code=nums[0],
                           title="Approve the sign-in")
                return True
            body = d.execute_script("return document.body ? document.body.innerText.slice(0, 1500) : ''") or ""
            if re.search(r"Approve sign.?in request|Check your Authenticator|notification to your", body, re.I):
                self._wait("Approve the sign-in request on your phone (Microsoft Authenticator).",
                           title="Approve the sign-in")
                return True
            # "Stay signed in?": yes, so it is not asked every day
            if re.search(r"Stay signed in\?", body):
                for el in d.find_elements(By.ID, "idSIButton9"):
                    if el.is_displayed():
                        el.click()
                        time.sleep(2)
                        return True
            # account picker: pick the only account, otherwise ask which one
            tiles = [t for t in d.find_elements(By.CSS_SELECTOR, "#tilesHolder [data-test-id], #tilesHolder .table")
                     if t.is_displayed()]
            if tiles:
                names = [t.text.strip().splitlines()[0] for t in tiles if t.text.strip()]
                if len(tiles) == 1:
                    tiles[0].click()
                    time.sleep(2)
                    return True
                answer = self.prompt("choose", title="Choose your account", message="Which Microsoft account?",
                                     options=[(str(i), n, "") for i, n in enumerate(names)], remember=False)
                if not answer:
                    return False
                tiles[int(answer[0])].click()
                time.sleep(2)
                return True
        return self._form_or_wait()

    # ------------------------------------------------------------ any form: ask for its fields in SALTO Buddy
    def _form_or_wait(self):
        try:
            fields = [f for f in (self.d.execute_script(_FIELDS_JS) or []) if not f["filled"]]
        except (WebDriverException, StaleElementReferenceException):
            return True
        if not fields:
            self.idle_since = self.idle_since or time.time()
            if time.time() - self.idle_since > 45 and not self.waiting:
                answer = self.prompt("choose", title="Still signing in", message="The sign-in is taking a while.",
                                     options=[("wait", "Keep waiting", "SALTO Buddy keeps going by itself."),
                                              ("show", "Show the Firefox window", "Finish the sign-in yourself.")],
                                     remember=False)
                self.idle_since = time.time()
                if not answer or answer[0] == "show":
                    return False
            return True
        self.idle_since = None
        self._wait(None)
        key = tuple(f["label"] for f in fields) + (self.d.current_url.split("?")[0],)
        error = ""
        with suppress(WebDriverException):
            error = self.d.execute_script(_ERROR_JS) or ""
        if key == self.last_form and not error:
            error = "That did not work. Please check and try again."
        self.last_form = key
        title = {"group": "Orange GroupIdentity", "microsoft": "Microsoft sign-in"}.get(self.method, "Sign in")
        answer = self.prompt("fields", title=title, message=self._page_hint(), error=error,
                             fields=[{"key": str(i), "label": f["label"], "secret": f["secret"]}
                                     for i, f in enumerate(fields)])
        if answer is None:
            return False
        for i, f in enumerate(fields):
            with suppress(WebDriverException):
                f["el"].clear()
                f["el"].send_keys(answer.get(str(i), ""))
        with suppress(WebDriverException):
            self._submit(fields[-1]["el"])
        time.sleep(3)
        return True

    def _page_hint(self):
        with suppress(WebDriverException):
            for xp in ("//h1", "//h2", "//*[@role='heading']", "//title"):
                for el in self.d.find_elements(By.XPATH, xp):
                    t = (el.text or "").strip()
                    if t and el.is_displayed():
                        return t[:120]
        return "Orange needs this to sign you in."

    def _submit(self, last_field):
        d = self.d
        for xp in ("//input[@type='submit' and not(@disabled)]", "//button[@type='submit' and not(@disabled)]",
                   "//*[@id='idSIButton9']",
                   "//button[contains(translate(normalize-space(.), 'NEXTSIGVERFYCONUB', 'nextsigverfyconub'), 'next')"
                   " or contains(translate(normalize-space(.), 'SIGN', 'sign'), 'sign in')"
                   " or contains(translate(normalize-space(.), 'VERIFY', 'verify'), 'verify')"
                   " or contains(translate(normalize-space(.), 'CONTINUE', 'continue'), 'continue')"
                   " or contains(translate(normalize-space(.), 'CONNECT', 'connect'), 'connect')"
                   " or contains(translate(normalize-space(.), 'SUBMIT', 'submit'), 'submit')]"):
            for el in d.find_elements(By.XPATH, xp):
                if el.is_displayed():
                    el.click()
                    return
        last_field.send_keys(Keys.ENTER)

    # ------------------------------------------------------------ the non-blocking message
    def _wait(self, message, code=None, title="Sign in to SALTO"):
        if message == self.waiting:
            return
        self.waiting = message
        if message:
            self.prompt("wait", title=title, message=message, code=code)
        else:
            self.prompt("close")
