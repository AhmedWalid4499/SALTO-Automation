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
from selenium.common.exceptions import (NoSuchElementException,
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


class LoginTimeout(RuntimeError):
    pass


class SaltoBrowser:
    def __init__(self, log=print, on_state=None):
        self.log = log
        self.driver = None
        # on_state(str) is told "starting", "signing-in", "connected" or "offline"
        self.on_state = on_state or (lambda _s: None)

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        if self.is_alive():
            return
        os.makedirs(PROFILE_DIR, exist_ok=True)
        opts = Options()
        if os.path.exists(FIREFOX_BIN):
            opts.binary_location = FIREFOX_BIN
        opts.add_argument("-profile")
        opts.add_argument(PROFILE_DIR)
        self.log("Starting Firefox...")
        self.on_state("starting")
        # The installed app ships geckodriver; from source, Selenium Manager fetches it
        bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "geckodriver.exe")
        service = Service(executable_path=bundled) if os.path.exists(bundled) else Service()
        service.creation_flags = 0x08000000  # CREATE_NO_WINDOW: no console flash
        self.driver = webdriver.Firefox(options=opts, service=service)
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
        d.get(SALTO_URL)
        deadline = time.time() + timeout
        asked = False
        while time.time() < deadline:
            d.switch_to.default_content()
            if self._portal_ready():
                self.log("Logged in to SALTO.")
                self.on_state("connected")
                return
            with suppress(NoSuchElementException, StaleElementReferenceException):
                link = d.find_element(By.XPATH, "//a[contains(normalize-space(.), 'Login with OpenID')]")
                self.log("Clicking 'Login with OpenID'...")
                link.click()
                time.sleep(3)
                continue
            if not self._on_salto() and self._choose_professional_account():
                time.sleep(3)
                continue
            if not asked and not self._on_salto():
                self.log("Please complete the sign-in in the Firefox window (waiting)...")
                asked = True
            time.sleep(1.5)
        raise LoginTimeout("Login was not completed in time.")

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
