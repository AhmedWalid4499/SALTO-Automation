"""SALTO Buddy's own sign-in windows (the prompt used by salto.signin): choose a method, fill in what the page
asks, wait for a PIN or a phone approval. Called from the browser thread; the windows live on the Tk thread."""
import threading
import tkinter as tk

from . import theme as T
from .dialogs import shell
from .widgets import RoundButton, RoundCard, RoundEntry, _scale


class SignInPrompter:
    def __init__(self, app):
        self.app = app
        self.wait_win = None

    def __call__(self, kind, **data):
        """Blocking for "choose" and "fields" (returns the answer), immediate for "wait" and "close"."""
        if kind in ("wait", "close"):
            self.app.ui(lambda: self._wait(data if kind == "wait" else None))
            return None
        box, done = {}, threading.Event()

        def show():
            try:
                box["answer"] = (self._choose if kind == "choose" else self._fields)(**data)
            finally:
                done.set()
        self.app.ui(show)
        done.wait()
        return box.get("answer")

    # ------------------------------------------------------------ choose a method / an option
    def _choose(self, title, message, options, remember=False):
        root = self.app.root
        self._bring_up()
        result = {"value": None}
        w, body, foot = shell(root, title, message, width=560)
        k = _scale(w)
        keep = tk.BooleanVar(value=True)
        for oid, label, desc in options:
            card = RoundCard(body, fill=T.FIELD, radius=16, pad=14, fit=True, shadow=False)
            card.pack(fill="x", pady=(0, 10))
            row = tk.Frame(card.inner, bg=T.FIELD, cursor="hand2")
            row.pack(fill="x")
            text = tk.Frame(row, bg=T.FIELD, cursor="hand2")
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=label, bg=T.FIELD, fg=T.INK, font=T.F_BOLD, anchor="w", cursor="hand2").pack(fill="x")
            if desc:
                tk.Label(text, text=desc, bg=T.FIELD, fg=T.MUTED, font=T.F_SMALL, anchor="w", justify="left",
                         wraplength=int(330 * k), cursor="hand2").pack(fill="x")

            def pick(_e=None, oid=oid):
                result["value"] = (oid, keep.get())
                w.destroy()
            RoundButton(row, "Choose", pick, padx=16, height=32).pack(side="right", padx=(10, 0), before=text)
            for widget in (card, card.inner, row, text, *text.winfo_children()):
                widget.bind("<Button-1>", pick)
        if remember:
            tk.Checkbutton(foot, text="Remember my choice", variable=keep, bg=T.CANVAS, activebackground=T.CANVAS,
                           font=T.F_SMALL, selectcolor=T.CARD).pack(side="left")
        RoundButton(foot, "Show Firefox instead", lambda: w.destroy(), kind="soft", padx=14,
                    height=32).pack(side="right")
        w.protocol("WM_DELETE_WINDOW", w.destroy)
        w.wait_window()
        return result["value"]

    # ------------------------------------------------------------ fields the sign-in page asks for
    def _fields(self, title, message, fields, error=""):
        root = self.app.root
        self._bring_up()
        result = {"value": None}
        w, body, foot = shell(root, title, message, width=500)
        if error:
            tk.Label(body, text=error, bg=T.CARD, fg=T.RED, font=T.F_SMALL, anchor="w", justify="left",
                     wraplength=int(400 * _scale(w))).pack(fill="x", pady=(0, 10))
        entries = {}
        for f in fields:
            tk.Label(body, text=f["label"], bg=T.CARD, fg=T.INK, font=T.F_SMALL_BOLD, anchor="w").pack(fill="x")
            var = tk.StringVar()
            e = RoundEntry(body, textvariable=var, width=380, show="•" if f.get("secret") else "")
            e.pack(fill="x", pady=(4, 12))
            entries[f["key"]] = var
            e.bind("<Return>", lambda _e: ok())
        tk.Label(body, text="Typed straight into the Orange sign-in page; never saved by SALTO Buddy.", bg=T.CARD,
                 fg=T.SUBTLE, font=T.F_SMALL, anchor="w", justify="left",
                 wraplength=int(380 * _scale(w))).pack(fill="x")

        def ok():
            result["value"] = {key: var.get() for key, var in entries.items()}
            for var in entries.values():  # forget the values in this window
                var.set("")
            w.destroy()
        RoundButton(foot, "Sign in", ok).pack(side="right")
        RoundButton(foot, "Show Firefox instead", w.destroy, kind="soft", padx=14).pack(side="right", padx=(0, 8))
        w.protocol("WM_DELETE_WINDOW", w.destroy)
        first = body.winfo_children()
        w.after(150, lambda: next((c.focus_set() for c in first if isinstance(c, RoundEntry)), None))
        w.wait_window()
        return result["value"]

    # ------------------------------------------------------------ "type your PIN" / "tap this number"
    def _wait(self, data):
        if self.wait_win is not None:
            try:
                self.wait_win.destroy()
            except tk.TclError:
                pass
            self.wait_win = None
        if not data:
            return
        self._bring_up()
        w, body, foot = shell(self.app.root, data.get("title", "Sign in to SALTO"), "", width=460, modal=False)
        tk.Label(body, text=data["message"], bg=T.CARD, fg=T.INK, font=T.F_BODY, justify="left", anchor="w",
                 wraplength=int(380 * _scale(w))).pack(fill="x")
        if data.get("code"):
            tk.Label(body, text=data["code"], bg=T.CARD, fg=T.ORANGE, font=(T.FONT, 36, "bold")).pack(pady=(10, 0))
        tk.Label(foot, text="Waiting for the sign-in...", bg=T.CANVAS, fg=T.MUTED, font=T.F_SMALL).pack(side="left")
        w.attributes("-topmost", True)
        self.wait_win = w

    def _bring_up(self):
        try:
            self.app.root.deiconify()
            self.app.root.lift()
        except tk.TclError:
            pass
