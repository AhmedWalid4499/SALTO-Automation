"""Fetch the Ask Buddy team key from the shared SharePoint/OneDrive folder link.

Uses SALTO Buddy's own Firefox (hidden), signed in with the user's Orange
Microsoft account (Windows single sign-on). The key is then cached on the PC,
encrypted with DPAPI, so this only happens once (or when the key is replaced).
The link is only open to Orange accounts, so it can live in the code.
"""
import base64
import time
from urllib.parse import parse_qs, urlparse

from selenium.common.exceptions import TimeoutException, WebDriverException

from . import errors
from .config import TEAM_KEY_FILE

TEAM_KEY_LINK = ("https://orange0-my.sharepoint.com/:f:/g/personal/ahmed_elbourgy_ext_orange_com/"
                 "IgBIet85KpwDSoTaxyAIlhvqAU5wFrH1Muf4zmBEifupeuw?e=Ad29gc")

# Runs inside the SharePoint page (same origin, the user's session): list the shared folder through the
# Shares API and read the key file; fall back to download.aspx with the folder path from the page URL.
_FETCH_JS = r"""
const [link, fileName, done] = arguments;
const enc = 'u!' + btoa(unescape(encodeURIComponent(link))).replace(/=+$/, '').replace(/\//g, '_').replace(/\+/g, '-');
(async () => {
  try {
    const r = await fetch('/_api/v2.0/shares/' + enc + '/driveItem/children?$top=200',
                          {headers: {Accept: 'application/json'}, credentials: 'include'});
    if (r.ok) {
      const items = (await r.json()).value || [];
      const it = items.find(i => (i.name || '').toLowerCase() === fileName);
      if (!it) return done({error: 'no ' + fileName + ' in the shared folder'});
      const url = it['@content.downloadUrl'] || it['@microsoft.graph.downloadUrl'];
      const f = await fetch(url, {credentials: 'include'});
      return done(f.ok ? {key: (await f.text()).replace(/^\uFEFF/, '').trim()} : {error: 'download ' + f.status});
    }
    const id = new URLSearchParams(location.search).get('id');
    if (!id) return done({error: 'shares api ' + r.status});
    const f = await fetch('/_layouts/15/download.aspx?SourceUrl=' + encodeURIComponent(id + '/' + fileName),
                          {credentials: 'include'});
    return done(f.ok ? {key: (await f.text()).replace(/^\uFEFF/, '').trim()} : {error: 'download.aspx ' + f.status});
  } catch (e) { done({error: String(e)}); }
})();
"""


def _get(d, url):
    """Navigate without waiting for SharePoint's heavy page to finish loading (it can take minutes)."""
    d.set_page_load_timeout(30)
    try:
        d.get(url)
    except TimeoutException:
        pass  # the page is usable (and the sign-in cookies are set) long before 'load' fires
    finally:
        d.set_page_load_timeout(300)


def _on_sharepoint(d):
    host = urlparse(d.current_url).hostname or ""
    return host.endswith(".sharepoint.com") and d.execute_script("return document.readyState") != "loading"


def fetch(b, link=TEAM_KEY_LINK, log=print, timeout=300):
    """Return the team key text, or raise RuntimeError with a readable reason."""
    b.start()
    d = b.driver
    d.switch_to.default_content()
    log("Ask Buddy: getting the team key from SharePoint...")
    _get(d, link)
    deadline, shown = time.time() + timeout, False
    stuck_since = time.time()
    while not _on_sharepoint(d):
        if time.time() > deadline:
            raise RuntimeError("Microsoft sign-in for the team folder was not completed")
        if b.headless and not shown and time.time() - stuck_since > 25:
            # Windows single sign-on did not do it: show Firefox so the user can sign in to Microsoft
            log("Ask Buddy: Microsoft needs you to sign in - opening the Firefox window...")
            b.quit()
            b.start(force_visible=True)
            d = b.driver
            _get(d, link)
            shown = True
        time.sleep(1)
        d = b.driver
    time.sleep(2)  # let the folder view settle (session cookies are set by now)
    d.set_script_timeout(60)
    try:
        res = d.execute_async_script(_FETCH_JS, link, TEAM_KEY_FILE.lower()) or {}
    except WebDriverException as exc:
        raise RuntimeError(f"could not read the team folder: {errors.note(exc)}")
    if not res.get("key"):
        raise RuntimeError(f"could not read the team key: {res.get('error', 'empty file')}")
    log("Ask Buddy: team key ready.")
    return res["key"]


def _b64_link(link):  # kept for reference/tests: the Shares API id of a sharing link
    return "u!" + base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")


def folder_path_from_url(url):
    return (parse_qs(urlparse(url).query).get("id") or [""])[0]
