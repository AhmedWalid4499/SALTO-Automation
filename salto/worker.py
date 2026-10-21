"""One background thread owns the browser; the GUI submits jobs to it.

Selenium is not thread-safe, so every browser call goes through here and the
Tk window never freezes while SALTO is loading.
"""
import queue
import threading

from . import errors
from .browser import SaltoBrowser


class BrowserWorker:
    def __init__(self, log, on_state=None, visible=False):
        self._jobs = queue.Queue()
        self.log = log
        self.browser = SaltoBrowser(log=log, on_state=on_state, visible=visible)
        threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, fn, on_done=None, on_error=None):
        """Run fn(browser) on the worker thread; callbacks run on that thread too."""
        self._jobs.put((fn, on_done, on_error))

    def _loop(self):
        while True:
            fn, on_done, on_error = self._jobs.get()
            if fn is None:
                break
            try:
                result = fn(self.browser)
                if on_done:
                    on_done(result)
            except Exception as exc:  # report to the GUI, keep the worker alive
                errors.record(exc)  # technical details: error.log only
                self.log(errors.friendly(exc))
                if on_error:
                    on_error(exc)

    def shutdown(self):
        self._jobs.put((lambda b: b.quit(), None, None))
        self._jobs.put((None, None, None))
