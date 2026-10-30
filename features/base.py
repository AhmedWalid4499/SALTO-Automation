"""Base class for a feature (one page in the sidebar).

To add a feature: create features/my_feature.py with a subclass of Feature,
then add it to FEATURES in features/__init__.py.
"""


class Feature:
    title = "Feature"
    icon = "\uE80F"          # glyph of Windows' icon font, shown in the menu
    subtitle = ""             # one line under the page title

    def __init__(self, app):
        self.app = app          # app.worker, app.log, app.ui (run on GUI thread), app.cfg

    def build(self, parent):
        """Build the page inside parent (a CTkFrame)."""
        raise NotImplementedError

    def run(self, fn, on_done=None, on_error=None, busy_widgets=()):
        """Run fn(browser) on the browser thread, then on_done(result) on the GUI thread."""
        for w in busy_widgets:
            w.configure(state="disabled")

        def done(result):
            self.app.ui(lambda: (self._unbusy(busy_widgets), on_done and on_done(result)))

        def failed(exc):
            self.app.ui(lambda: (self._unbusy(busy_widgets), on_error and on_error(exc)))

        self.app.worker.submit(fn, done, failed)

    @staticmethod
    def _unbusy(widgets):
        for w in widgets:
            w.configure(state="normal")
