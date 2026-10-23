"""Firefox session for SALTO (Pega) driven by Selenium.

Pega renders each portal tab (My Work, STC Search, a case...) inside its own
iframe, so most helpers here search across frames and leave the driver
switched into the frame where the element was found.
"""
import os
import sys
import time
from contextlib import suppress
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import (ElementClickInterceptedException,
                                        NoSuchElementException,
                                        StaleElementReferenceException,
                                        WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

SALTO_URL = ("https://web-salto-intl.com.intraorange/prweb/PRAuth/app/OFA_/"
             "msHWMWNvhSu2obrHYvzNGg*/!STANDARD")
FIREFOX_BIN = r"C:\Program Files\Mozilla Firefox\firefox.exe"
# Dedicated profile so the tool never fights with your everyday Firefox
# (a profile can only be open in one Firefox at a time).
PROFILE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "SaltoTool", "firefox-profile")
# Firefox saves every download here without asking; salto.files moves each file into the order folder
DOWNLOAD_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "SaltoBuddy", "downloads")
_SAVE_MIME = ",".join([
    "application/pdf", "application/octet-stream", "application/zip", "application/x-zip-compressed",
    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-outlook", "message/rfc822", "text/csv", "text/plain", "text/xml", "application/xml",
    "image/png", "image/jpeg", "image/gif", "application/vnd.visio", "application/x-msg",
])

# Pega's grey overlay while it is busy: it swallows clicks (here, or in the top page)
_MASK_JS = r"""
const shown = doc => [...doc.querySelectorAll('#screen-layout-mask, .screen-layout-mask')].some(m => {
  const s = getComputedStyle(m); return m.offsetWidth && s.display !== 'none' && s.visibility !== 'hidden'; });
let top = false; try { top = window.top !== window && shown(window.top.document); } catch (e) {}
return shown(document) || top;
"""


class LoginTimeout(RuntimeError):
    pass


class SaltoBrowser:
    def __init__(self, log=print, on_state=None, visible=False):
        self.log = log
        self.driver = None
        # on_state(str) is told "starting", "signing-in", "connected" or "offline"
        self.on_state = on_state or (lambda _s: None)
        self.visible = visible       # user setting: show the Firefox window
        self.headless = False        # how the running Firefox was started
        # sign-in in SALTO Buddy's own windows (ui.signin): prompt(kind, **data); None: show Firefox instead
        self.prompt = None
        self.cfg = None              # app settings (remembered sign-in method)

    def set_visible(self, visible):
        """Takes effect the next time Firefox starts (a running Firefox cannot be hidden/shown)."""
        self.visible = visible
        if self.driver and self.headless == visible:
            self.quit()

    # ------------------------------------------------------------------ lifecycle
    def start(self, force_visible=False):
        if self.is_alive():
            return
        os.makedirs(PROFILE_DIR, exist_ok=True)
        opts = Options()
        if os.path.exists(FIREFOX_BIN):
            opts.binary_location = FIREFOX_BIN
        opts.add_argument("-profile")
        opts.add_argument(PROFILE_DIR)
        self.headless = not (self.visible or force_visible)
        if self.headless:  # runs in the background; a full-HD size so SALTO lays out like on a desktop
            for a in ("-headless", "--width=1920", "--height=1080"):
                opts.add_argument(a)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        for k, v in {"browser.download.folderList": 2, "browser.download.dir": DOWNLOAD_DIR,
                     "browser.download.useDownloadDir": True, "browser.download.alwaysOpenPanel": False,
                     "browser.download.always_ask_before_handling_new_types": False,
                     "browser.helperApps.neverAsk.saveToDisk": _SAVE_MIME, "pdfjs.disabled": True,
                     # intranet names only resolve through the corporate DNS: never use DNS-over-HTTPS
                     "network.trr.mode": 5,
                     # sign in to Microsoft 365 (team key on SharePoint) with the Windows Orange account
                     "network.http.windows-sso.enabled": True,
                     # Orange PKI: use the Windows certificate store (PKI card) and pick the certificate without
                     # a Firefox dialog; Windows itself asks for the PIN
                     "security.osclientcerts.autoload": True,
                     "security.default_personal_cert": "Select Automatically"}.items():
            opts.set_preference(k, v)
        self.log("Starting Firefox...")
        self.on_state("starting")
        # The installed app ships geckodriver; from source, Selenium Manager fetches it
        bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "geckodriver.exe")
        service = Service(executable_path=bundled) if os.path.exists(bundled) else Service()
        service.creation_flags = 0x08000000  # CREATE_NO_WINDOW: no console flash
        self.driver = webdriver.Firefox(options=opts, service=service)
        if self.headless:
            self.driver.set_window_size(1920, 1080)
        else:
            self.driver.maximize_window()

    def is_alive(self):
        if not self.driver:
            return False
        try:
            self.driver.title  # noqa: B018 - cheap liveness probe
            return True
        except WebDriverException:
            self.driver = None
            self.on_state("offline")
            return False

    def quit(self):
        if self.driver:
            with suppress(WebDriverException):
                self.driver.quit()
            self.driver = None
        self.on_state("offline")

    # ------------------------------------------------------------------ login
    def ensure_logged_in(self, timeout=600):
        """Open SALTO and wait until the portal is usable.

        Clicks "Login with OpenID" on the Pega login page and the
        professional-account option on Orange Connect. Anything further
        (password, MFA) is left to you in the Firefox window.
        """
        self.start()
        d = self.driver
        d.switch_to.default_content()
        if self._portal_ready():
            self.on_state("connected")
            return
        self.on_state("signing-in")
        self._open_salto(timeout)
        deadline = time.time() + timeout
        asked = False
        stuck_since = None
        signin = None
        use_app = self.prompt is not None and self.headless  # sign in through SALTO Buddy's windows
        while time.time() < deadline:
            d = self.driver
            d.switch_to.default_content()
            if self._portal_ready():
                if signin:
                    signin.done()
                self.log("Logged in to SALTO.")
                self.on_state("connected")
                return
            with suppress(NoSuchElementException, StaleElementReferenceException):
                link = d.find_element(By.XPATH, "//a[contains(normalize-space(.), 'Login with OpenID')]")
                self.log("Clicking 'Login with OpenID'...")
                link.click()
                time.sleep(3)
                continue
            if use_app and not self._on_salto():
                from .signin import SignIn
                signin = signin or SignIn(self, self.prompt, self.cfg, self.log)
                try:
                    keep = signin.step()
                except WebDriverException:
                    keep = True  # the page changed under us: look again
                if keep:
                    time.sleep(1.5)
                    continue
                # the user wants to finish in Firefox
                signin.done()
                use_app, signin = False, None
                self.log("Opening the Firefox window for the sign-in...")
                self.quit()
                self.start(force_visible=True)
                self.on_state("signing-in")
                self._open_salto(timeout)
                continue
            if not self._on_salto() and self._choose_professional_account():
                time.sleep(3)
                continue
            if self._on_salto() and self._pega_error_page():
                # Pega's "There has been an issue" after an interrupted sign-in hand-off: open SALTO again
                self.log("SALTO showed an error page after sign-in; opening it again...")
                self._open_salto(timeout)
                time.sleep(3)
                continue
            if not self._on_salto():
                stuck_since = stuck_since or time.time()
                if self.headless and time.time() - stuck_since > 20:
                    # the sign-in wants the user (password / MFA): bring Firefox up so they can finish it
                    self.log("The Orange sign-in needs you: opening the Firefox window...")
                    self.quit()
                    self.start(force_visible=True)
                    self.on_state("signing-in")
                    self._open_salto(timeout)
                    stuck_since = None
                    continue
                if not asked and not self.headless:
                    self.log("Please complete the sign-in in the Firefox window (waiting)...")
                    asked = True
            time.sleep(1.5)
        raise LoginTimeout("Login was not completed in time.")

    def _open_salto(self, timeout):
        """Load SALTO, waiting out network/VPN drops instead of failing."""
        deadline, warned = time.time() + timeout, False
        while True:
            try:
                self.driver.get(SALTO_URL)
                return
            except WebDriverException as exc:
                if "neterror" not in str(exc) or time.time() > deadline:
                    raise
                if not warned:
                    self.log("SALTO is unreachable (VPN / network?). Waiting for the connection...")
                    self.on_state("offline-network")
                    warned = True
                time.sleep(10)

    def _pega_error_page(self):
        try:
            return "There has been an issue" in (self.driver.execute_script(
                "return document.body ? document.body.innerText.slice(0, 500) : ''") or "")
        except WebDriverException:
            return False

    def _choose_professional_account(self):
        """On the Orange Connect page, pick the professional-account option.

        Only selects the option; it never types credentials.
        """
        xp = ("//*[self::button or self::a or @role='button' or self::input[@type='submit']]"
              "[contains(translate(normalize-space(.), 'PROFESIONAL', 'profesional'), 'professional')"
              " or contains(translate(@value, 'PROFESIONAL', 'profesional'), 'professional')]")
        for el in self.driver.find_elements(By.XPATH, xp):
            with suppress(WebDriverException):
                if el.is_displayed():
                    self.log("Choosing 'Connect with professional account'...")
                    el.click()
                    return True
        return False

    def _on_salto(self):
        # compare the host only: the Orange login URL embeds SALTO's address in redirect_uri
        return urlparse(self.driver.current_url).hostname == "web-salto-intl.com.intraorange"

    def _portal_ready(self):
        try:
            return self._on_salto() and bool(
                self.driver.find_elements(By.XPATH, "//*[@title='Toggle Left Navigation' or @aria-label='Toggle Left Navigation']"))
        except WebDriverException:
            return False

    # ------------------------------------------------------------------ frames
    def frames(self):
        """Yield after switching into the top document and every iframe (2 levels)."""
        d = self.driver
        d.switch_to.default_content()
        yield
        top = d.find_elements(By.TAG_NAME, "iframe")
        for i in range(len(top)):
            d.switch_to.default_content()
            fr = d.find_elements(By.TAG_NAME, "iframe")
            if i >= len(fr):
                break
            with suppress(WebDriverException):
                if not fr[i].is_displayed():  # hidden Pega tab
                    continue
                d.switch_to.frame(fr[i])
                yield
                inner = d.find_elements(By.TAG_NAME, "iframe")
                for j in range(len(inner)):
                    d.switch_to.default_content()
                    d.switch_to.frame(d.find_elements(By.TAG_NAME, "iframe")[i])
                    sub = d.find_elements(By.TAG_NAME, "iframe")
                    if j >= len(sub):
                        break
                    with suppress(WebDriverException):
                        if not sub[j].is_displayed():
                            continue
                        d.switch_to.frame(sub[j])
                        yield

    def find_visible(self, xpath, timeout=20):
        """Find the first displayed element matching xpath in any frame."""
        deadline = time.time() + timeout
        while True:
            for _ in self.frames():
                for el in self.driver.find_elements(By.XPATH, xpath):
                    with suppress(StaleElementReferenceException):
                        if el.is_displayed():
                            return el
            if time.time() > deadline:
                raise NoSuchElementException(f"Not found: {xpath}")
            time.sleep(0.5)

    def click(self, el, timeout=30):
        """Click like a user, once SALTO's grey 'loading' mask is gone; a script click if something still covers el."""
        d = self.driver
        deadline = time.time() + timeout
        while time.time() < deadline and d.execute_script(_MASK_JS):
            time.sleep(0.3)
        for _ in range(3):
            try:
                el.click()
                return
            except ElementClickInterceptedException:
                time.sleep(1)
        d.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", el)

    def frame_with_text(self, *texts, timeout=30):
        """Switch into the displayed frame whose text contains all given strings."""
        deadline = time.time() + timeout
        while True:
            for _ in self.frames():
                with suppress(WebDriverException):
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    if body.is_displayed() and body.size["height"] > 0:
                        txt = self.driver.execute_script("return document.body.textContent || ''")
                        if all(t in txt for t in texts):
                            return
            if time.time() > deadline:
                raise NoSuchElementException(f"No frame containing {texts}")
            time.sleep(0.7)

    def screenshot(self, path):
        self.driver.switch_to.default_content()
        self.driver.save_screenshot(path)
        return path
