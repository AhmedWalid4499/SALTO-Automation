"""SALTO Buddy - desktop app.

Run from source:  py app.py
"""
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import filedialog, ttk

from features import FEATURES
from salto import config, errors, keystore, updater
from salto.version import APP_NAME, __version__
from salto.worker import BrowserWorker
from ui import dialogs as messagebox  # SALTO Buddy-styled messages
from ui import guide, notify
from ui.signin import SignInPrompter
from ui import theme as T
from ui.widgets import NavItem, Pill, RoundButton, RoundCard

PILL = {  # browser state -> (text, dot colour)
    "offline": ("Ready", T.GREEN),
    "starting": ("Starting Firefox...", T.ORANGE),
    "signing-in": ("Signing in to SALTO...", T.ORANGE),
    "connected": ("Connected to SALTO", T.GREEN),
    "offline-network": ("Offline - waiting for network", T.PILL_OFFLINE),
}
ERROR_LOG = os.path.join(config.CONFIG_DIR, "error.log")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = config.load()
        self._ui_q = queue.Queue()
        self._log_lines = []
        self._update = None
        self._busy = 0
        self._state = "offline"
        self.on_log = []

        root.title(APP_NAME)
        root.geometry("1240x800")
        root.minsize(1040, 660)
        ico = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets", "app.ico")
        if os.path.exists(ico):
            root.iconbitmap(default=ico)  # default=: every dialog gets the SALTO Buddy icon too
        T.setup(root)
        root.report_callback_exception = self._report

        self.worker = BrowserWorker(log=self.log, on_state=lambda s: self.ui(lambda: self._set_state(s)),
                                    visible=self.cfg.get("show_browser", False))
        # Orange sign-in in SALTO Buddy's own windows instead of showing Firefox
        self.worker.browser.prompt = SignInPrompter(self)
        self.worker.browser.cfg = self.cfg
        self.worker.browser.save_cfg = lambda: self.ui(lambda: config.save(self.cfg))
        self.reports = {}      # order_ref -> OrderReport read this session (shared by the features)
        self.explorer = None   # the Order explorer feature (Ask Buddy opens orders through it)
        self.features, self.pages, self.nav = [], [], []

        self._sidebar()
        main = tk.Frame(root, bg=T.CANVAS)
        main.pack(side="left", fill="both", expand=True, padx=(4, 18), pady=(14, 0))
        top = tk.Frame(main, bg=T.CANVAS)
        top.pack(fill="x", pady=(4, 10))
        self.page_title = tk.Label(top, text="", bg=T.CANVAS, fg=T.INK, font=T.F_PAGE, anchor="w")
        self.page_title.pack(anchor="w")
        self.page_sub = tk.Label(top, text="", bg=T.CANVAS, fg=T.MUTED, font=T.F_SMALL, anchor="w")
        self.page_sub.pack(anchor="w")
        self._statusbar(main)
        for i, cls in enumerate(FEATURES):
            card = RoundCard(main, radius=28, pad=20)
            f = cls(self)
            if cls.__name__ == "OrderExplorer":
                self.explorer = f
            f.build(card.inner)
            self.features.append(f)
            self.pages.append(card)
        self.select(0)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(80, self._pump)
        if self.cfg.get("check_updates_on_start", True):
            root.after(1500, lambda: self.check_updates(silent=True))
        root.after(3000, self._find_team_key)
        # warm up: start Firefox and sign in to SALTO now, so the first order does not wait for it
        root.after(800, lambda: self.worker.submit(lambda b: b.ensure_logged_in(), on_error=lambda e: None))
        if self.cfg.get("seen_version") != __version__:  # first start after install / update: walkthrough
            root.after(1200, self._whats_new)

    def _whats_new(self):
        self.cfg["seen_version"] = __version__
        config.save(self.cfg)
        guide.show_whats_new(self)

    def _find_team_key(self):
        """If there is no usable key yet, look for the team key in this PC's synced SharePoint/OneDrive folders."""
        if keystore.unprotect(self.cfg.get("claude_key", "")) or config.read_team_key(self.cfg):
            return

        def work():
            folder = config.find_team_key()
            if folder:
                def found():
                    self.cfg["team_key_dir"] = config.portable(folder)
                    config.save(self.cfg)
                    self.log(f"SALTO Bot: found the team key in {folder}", quiet=True)
                    for feat in self.features:
                        getattr(feat, "key_changed", lambda: None)()
                self.ui(found)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ chrome
    def _sidebar(self):
        k = max(1.0, self.root.winfo_fpixels("1i") / 96)  # Windows display scaling
        side = RoundCard(self.root, radius=28, pad=14, width=int(208 * k))
        side.pack(side="left", fill="y", padx=(18, 14), pady=18)
        side.pack_propagate(False)
        box = side.inner
        brand = tk.Frame(box, bg=T.CARD)
        brand.pack(fill="x", padx=6, pady=(8, 22))
        px = 64 if k >= 1.4 else 48 if k > 1.15 else 40
        logo = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets",
                            f"logo_{px}.png")
        if os.path.exists(logo):
            self._logo = tk.PhotoImage(file=logo)
            tk.Label(brand, image=self._logo, bg=T.CARD).pack(side="left")
        names = tk.Frame(brand, bg=T.CARD)
        names.pack(side="left", padx=(10, 0))
        tk.Label(names, text=APP_NAME, bg=T.CARD, fg=T.INK, font=T.F_SECTION).pack(anchor="w")
        tk.Label(names, text="for SALTO", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL).pack(anchor="w")

        tk.Label(box, text="MENU", bg=T.CARD, fg=T.SUBTLE, font=T.F_CAPS).pack(anchor="w", padx=12, pady=(0, 6))
        for i, cls in enumerate(FEATURES):
            item = NavItem(box, getattr(cls, "icon", "\uE80F"), getattr(cls, "nav_title", cls.title),
                           lambda i=i: self.select(i))
            item.pack(fill="x", pady=1)
            self.nav.append(item)

        bottom = tk.Frame(box, bg=T.CARD)
        bottom.pack(side="bottom", fill="x")
        tk.Label(bottom, text="SUPPORT", bg=T.CARD, fg=T.SUBTLE, font=T.F_CAPS).pack(anchor="w", padx=12,
                                                                                  pady=(0, 6))
        NavItem(bottom, "\uE897", "Guide", lambda: guide.show_guide(self.root)).pack(fill="x", pady=1)
        NavItem(bottom, "\uE713", "Settings", self.show_settings).pack(fill="x", pady=1)
        self.update_item = NavItem(bottom, "\uE896", "Check for updates",
                                   lambda: self.prompt_update() if self._update else self.check_updates(False))
        self.update_item.pack(fill="x", pady=1)
        self.pill = Pill(bottom)
        self.pill.pack(fill="x", pady=(14, 4))
        tk.Label(bottom, text=f"Version {__version__}", bg=T.CARD, fg=T.SUBTLE, font=T.F_SMALL).pack(anchor="w",
                                                                                                padx=12)

    def select(self, index):
        """Show one feature page (sidebar click)."""
        for i, (card, item) in enumerate(zip(self.pages, self.nav)):
            item.set(selected=i == index)
            if i != index:
                card.pack_forget()
        cls = FEATURES[index]
        self.page_title.configure(text=cls.title)
        self.page_sub.configure(text=getattr(cls, "subtitle", ""))
        self.pages[index].pack(fill="both", expand=True, pady=(0, 10))
        self.current = self.features[index] if index < len(self.features) else None

    def _statusbar(self, parent):
        bar = tk.Frame(parent, bg=T.CANVAS)
        bar.pack(side="bottom", fill="x", pady=(0, 8))
        top = tk.Frame(bar, bg=T.CANVAS)
        top.pack(fill="x")
        self.status = tk.Label(top, text="Ready", bg=T.CANVAS, fg=T.MUTED, font=T.F_SMALL, anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=4)
        self.log_link = tk.Label(top, text="Show activity", bg=T.CANVAS, fg=T.ORANGE, font=T.F_SMALL_BOLD,
                                 cursor="hand2")
        self.log_link.pack(side="right", padx=4)
        self.log_link.bind("<Button-1>", lambda e: self.toggle_log())
        self.logbox = tk.Text(bar, height=7, font=T.F_LOG, bg=T.CARD, fg=T.INK, borderwidth=0,
                              highlightthickness=0, padx=12, pady=8, state="disabled")

    def toggle_log(self):
        if self.logbox.winfo_ismapped():
            self.logbox.pack_forget()
            self.log_link.configure(text="Show activity")
        else:
            self.logbox.pack(fill="x", pady=(0, 6))
            self.logbox.see("end")
            self.log_link.configure(text="Hide activity")

    def _set_state(self, s):
        self._state = s
        if not self._busy or s == "offline-network":
            self.pill.set(*PILL.get(s, PILL["offline"]))

    def notify(self, title, message, page=None, kind="done", only_if_away=False):
        """A 'task done' notification (Settings > Notify me...). page: feature to show when it is clicked.
        only_if_away: only when the user is not already looking at that page in SALTO Buddy."""
        if not self.cfg.get("notify", True):
            return
        on_page = page is not None and getattr(self, "current", None) is page
        if only_if_away and notify.app_active(self.root) and (page is None or on_page):
            return
        open_page = (lambda: self.select(self.features.index(page))) if page in self.features else (lambda: None)
        notify.show(self.root, title, message, on_open=open_page, kind=kind,
                    sound=self.cfg.get("notify_sound", False))

    def busy(self, on, text=""):
        """Features call this around long work: orange pill, wait cursor."""
        self._busy = max(0, self._busy + (1 if on else -1))
        if self._busy:
            self.pill.set(text or "Working...", T.ORANGE)
            self.root.configure(cursor="watch")
        else:
            self.pill.set(*PILL.get(self._state, PILL["offline"]))
            self.root.configure(cursor="")

    # ------------------------------------------------------------ thread-safe GUI access
    def ui(self, fn):
        self._ui_q.put(fn)

    def _pump(self):
        while not self._ui_q.empty():
            try:
                self._ui_q.get()()
            except Exception:
                self._report(*sys.exc_info())
        self.root.after(80, self._pump)

    def log(self, msg, quiet=False):
        """quiet=True: activity log only, not the status bar."""
        line = f"[{datetime.now():%H:%M:%S}] {msg}"

        def write():
            self._log_lines.append(line)
            if not quiet:
                self.status.configure(text=msg[:160])
            if self._busy and not quiet:
                self.pill.set(msg[:48], T.ORANGE)
            self.logbox.configure(state="normal")
            self.logbox.insert("end", line + "\n")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
            for cb in self.on_log:
                cb(msg)
        self.ui(write)

    def _report(self, exc, val, tb):
        os.makedirs(config.CONFIG_DIR, exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n" + "".join(traceback.format_exception(exc, val, tb)))
        messagebox.showerror(APP_NAME, f"Something went wrong. {errors.friendly(val)}")

    # ------------------------------------------------------------ settings
    def show_settings(self):
        w, body = self._dialog("Settings", 640, "Folders, what SALTO Buddy reads, notifications and the SALTO Bot")
        tabs = ttk.Notebook(body, style="Inner.TNotebook")
        tabs.pack(fill="both", expand=True)
        f = ttk.Frame(tabs, style="Card.TFrame", padding=(4, 12, 4, 4))
        tabs.add(f, text="General")
        ask = ttk.Frame(tabs, style="Card.TFrame", padding=(4, 12, 4, 4))
        tabs.add(ask, text="SALTO Bot")
        ttk.Label(f, text="Folders", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Save folder (each order gets '<order> - <STC>' with Downloads and Screenshots)",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 2))
        folder = tk.StringVar(value=self.cfg["export_dir"])
        ttk.Entry(f, textvariable=folder, width=52).grid(row=2, column=0, sticky="ew")
        ttk.Button(f, text="Browse", command=lambda: folder.set(
            filedialog.askdirectory(initialdir=folder.get(), parent=w) or folder.get())).grid(row=2, column=1, padx=6)
        ttk.Button(f, text="Open", command=lambda: (os.makedirs(folder.get(), exist_ok=True),
                                                    os.startfile(folder.get()))).grid(row=2, column=2)
        ttk.Label(f, text="Defaults", style="Section.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(16, 4))
        opts = {}
        for i, (k, text) in enumerate([("show_browser", "Show the Firefox window (normally it works hidden)"),
                                       ("subcases", "Open every sub-case (EQP, CONF, SG, INV...)"),
                                       ("downloads", "Download all attachments automatically while reading"),
                                       ("tab_screenshots", "Screenshot every tab while reading"),
                                       ("flip", "Get serial numbers from FLIP for EQPs"),
                                       ("full_audit", "Read the full audit history (slower)"),
                                       ("check_updates_on_start", "Check for updates when SALTO Buddy starts"),
                                       ("notify", "Notify me when a task is done (order read, answer ready, downloads)"),
                                       ("notify_sound", "Play a sound with notifications")]):
            opts[k] = tk.BooleanVar(value=self.cfg.get(k, config.DEFAULTS.get(k, True)))
            ttk.Checkbutton(f, text=text, variable=opts[k]).grid(row=4 + i, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(f, text="Sign in to SALTO with", style="Section.TLabel").grid(row=14, column=0, columnspan=3,
                                                                              sticky="w", pady=(16, 4))
        from salto.signin import METHODS
        choices = [("", "Ask me when Orange needs it")] + [(m[0], m[1]) for m in METHODS]
        signin = tk.StringVar(value=dict(choices).get(self.cfg.get("signin_method", ""), choices[0][1]))
        ttk.Combobox(f, textvariable=signin, values=[c[1] for c in choices], state="readonly", width=40).grid(
            row=15, column=0, sticky="w")
        ttk.Label(f, text="SALTO Buddy asks in its own window and signs you in; Firefox stays hidden.",
                  style="Muted.TLabel").grid(row=16, column=0, columnspan=3, sticky="w", pady=(2, 0))
        f.columnconfigure(0, weight=1)

        # Ask Buddy: Claude API key, stored encrypted for this Windows user (DPAPI) - its own tab
        f = ask
        f.columnconfigure(0, weight=1)
        ttk.Label(f, text="The Friendly SALTO Bot", style="Section.TLabel").grid(row=13, column=0, columnspan=3, sticky="w", pady=(16, 4))
        ttk.Label(f, text="Claude API key (from console.anthropic.com). Questions and the order data they need are "
                          "sent to Anthropic.", style="Muted.TLabel", wraplength=500).grid(row=14, column=0, columnspan=3,
                                                                                           sticky="w")
        has_key = bool(keystore.unprotect(self.cfg.get("claude_key", "")))
        key = tk.StringVar()
        key_entry = ttk.Entry(f, textvariable=key, show="•", width=52)
        key_entry.grid(row=15, column=0, sticky="ew", pady=(4, 0))
        if has_key:
            key_entry.insert(0, "(saved - type a new key to replace it)")
            key_entry.configure(show="")
            key_entry.bind("<FocusIn>", lambda e: (key.set("") if key.get().startswith("(saved") else None,
                                                   key_entry.configure(show="•")))
        key_state = ttk.Label(f, text="Key saved" if has_key else "No key yet", style="Muted.TLabel")
        key_state.grid(row=16, column=0, columnspan=3, sticky="w")

        def test_key():
            k = key.get().strip()
            if not k or k.startswith("(saved"):
                k = (keystore.unprotect(self.cfg.get("claude_key", ""))
                     or config.read_team_key({"team_key_dir": team_dir.get().strip()}))
            if not k:
                key_state.configure(text="Type a key first (or set the team key folder below)")
                return
            key_state.configure(text="Checking...")

            def work():
                from salto.assistant import check_key
                try:
                    check_key(k)
                    msg = "Key works"
                except Exception as exc:
                    msg = f"Key check failed: {str(exc).splitlines()[0][:90]}"
                self.ui(lambda: key_state.configure(text=msg))
            threading.Thread(target=work, daemon=True).start()
        ttk.Button(f, text="Test", command=test_key).grid(row=15, column=1, padx=6, pady=(4, 0))
        ttk.Button(f, text="Remove", command=lambda: (key.set(""), self.cfg.update(claude_key=""),
                                                     key_state.configure(text="Key removed"))).grid(row=15, column=2,
                                                                                                     pady=(4, 0))

        # team key: one file in a team-only folder, read by everyone's SALTO Buddy
        ttk.Label(f, text="Team key folder (only Orange staff can open it). Leave your own key empty to use the "
                          "team key.", style="Muted.TLabel", wraplength=500).grid(row=17, column=0, columnspan=3,
                                                                                  sticky="w", pady=(10, 0))
        team_dir = tk.StringVar(value=os.path.expandvars(self.cfg.get("team_key_dir") or config.TEAM_KEY_DIR))
        ttk.Entry(f, textvariable=team_dir, width=52).grid(row=18, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(f, text="Browse", command=lambda: team_dir.set(
            filedialog.askdirectory(initialdir=team_dir.get() or None, parent=w) or team_dir.get())).grid(
            row=18, column=1, padx=6, pady=(4, 0))
        team_state = ttk.Label(f, text="", style="Muted.TLabel")
        team_state.grid(row=19, column=0, columnspan=3, sticky="w")

        def team_status():
            p = config.team_key_path({"team_key_dir": team_dir.get().strip()})
            team_state.configure(text=("Team key found" if p and config.read_team_key({"team_key_dir": team_dir.get()})
                                       else "No team key in this folder" if p else "No team folder set"))
        team_status()
        team_dir.trace_add("write", lambda *_a: team_status())

        def save_team_key():
            k = key.get().strip()
            if not k or k.startswith("(saved"):
                k = keystore.unprotect(self.cfg.get("claude_key", ""))
            folder_ = team_dir.get().strip()
            if not k or not folder_:
                messagebox.showinfo(APP_NAME, "Type the key above and choose the team folder first.", parent=w)
                return
            path = config.team_key_path({"team_key_dir": folder_})
            if not messagebox.askyesno(APP_NAME, f"Save the key for everyone who can open:\n{folder_}\n\n"
                                                 "Anyone with access to this folder can use (and be billed on) this key. "
                                                 "Continue?", parent=w):
                return
            try:
                os.makedirs(folder_, exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(k + "\n")
            except OSError as exc:
                messagebox.showerror(APP_NAME, f"Could not write {path}:\n{exc}", parent=w)
                return
            team_status()
        ttk.Button(f, text="Save as team key", command=save_team_key).grid(row=18, column=2, pady=(4, 0))

        foot = ttk.Frame(body, style="Card.TFrame")
        foot.pack(fill="x", pady=(14, 0))
        ttk.Label(foot, text=f"Version {__version__}  ·  © 2026 Ahmed Walid", style="Muted.TLabel").pack(side="left")

        def save():
            self.cfg["export_dir"] = folder.get().strip() or config.DEFAULTS["export_dir"]
            self.cfg["signin_method"] = {label: key for key, label in choices}.get(signin.get(), "")
            for k, v in opts.items():
                self.cfg[k] = bool(v.get())
            new_key = key.get().strip()
            if new_key and not new_key.startswith("(saved"):
                self.cfg["claude_key"] = keystore.protect(new_key)
            td = team_dir.get().strip()
            self.cfg["team_key_dir"] = "" if td == config.TEAM_KEY_DIR else config.portable(td)
            config.save(self.cfg)
            for feat in self.features:
                getattr(feat, "key_changed", lambda: None)()
            for feat in self.features:
                getattr(feat, "settings_changed", lambda: None)()
            w.destroy()
        RoundButton(foot, "Done", save).pack(side="right")

    def _dialog(self, title, width, subtitle=""):
        """A SALTO Buddy window over the app: (window, body)."""
        w, body, _foot = messagebox.shell(self.root, title, subtitle, width=width)
        return w, body

    # ------------------------------------------------------------ updates (GitHub releases)
    def check_updates(self, silent):
        def work():
            try:
                info = updater.check()
            except Exception as exc:
                self.log(f"Update check failed: {exc}", quiet=silent)
                if not silent:
                    self.ui(lambda e=exc: messagebox.showwarning(APP_NAME, f"Could not reach GitHub to check for updates.\n\n{e}"))
                return
            self.ui(lambda: self._on_update(info, silent))
        threading.Thread(target=work, daemon=True).start()

    def _on_update(self, info, silent):
        self._update = info
        if not info:
            if not silent:
                messagebox.showinfo(APP_NAME, f"You're up to date (version {__version__}).")
            return
        self.update_item.set(text=f"Update to {info.version}", badge=True)
        self.log(f"Update available: {info.version}")
        if not silent or self.cfg.get("skipped_version") != info.version:
            self.prompt_update()

    def prompt_update(self):
        info = self._update
        if not info:
            return
        w, body = self._dialog("Update available", 560, f"You have version {__version__}")
        f = ttk.Frame(body, style="Card.TFrame")
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"SALTO Buddy {info.version} is available", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text=f"You have {__version__}. What's new:", style="Muted.TLabel").pack(anchor="w", pady=(2, 6))
        notes = tk.Text(f, height=9, width=60, wrap="word", font=T.F_BODY, bg=T.FIELD, borderwidth=0,
                        highlightthickness=0, padx=12, pady=10)
        notes.insert("end", info.notes or "No release notes.")
        notes.configure(state="disabled")
        notes.pack(fill="x")
        bar = ttk.Progressbar(f, mode="determinate", maximum=1.0)
        status = ttk.Label(f, text="", style="Muted.TLabel")
        foot = ttk.Frame(f, style="Card.TFrame")
        foot.pack(fill="x", pady=(14, 0))

        def later():
            self.cfg["skipped_version"] = info.version
            config.save(self.cfg)
            w.destroy()

        def go():
            if not updater.frozen():
                messagebox.showinfo(APP_NAME, "Running from source: pull the latest code from GitHub instead.", parent=w)
                return
            dl.configure(state="disabled", text="Downloading...")
            bar.pack(fill="x", pady=(10, 0), before=foot)
            status.pack(anchor="w", before=foot)

            def progress(done, total):
                self.ui(lambda: (bar.configure(value=done / total if total else 0),
                                 status.configure(text=f"Downloading update... {int(100 * done / total) if total else 0}%"),
                                 self.pill.set(f"Downloading update... {int(100 * done / total) if total else 0}%", T.ORANGE)))

            def work():
                try:
                    path = updater.download(info, progress)
                except Exception as exc:
                    self.ui(lambda e=exc: (messagebox.showerror(APP_NAME, f"Download failed: {e}", parent=w),
                                     dl.configure(state="normal", text="Download and install")))
                    return
                self.ui(lambda: self._install(path))
            threading.Thread(target=work, daemon=True).start()

        dl = ttk.Button(foot, text="Download and install", style="Accent.TButton", command=go)
        dl.pack(side="right")
        ttk.Button(foot, text="Later", command=later).pack(side="right", padx=8)
        if info.page:
            ttk.Button(foot, text="Release page", command=lambda: os.startfile(info.page)).pack(side="left")

    def _install(self, path):
        try:
            updater.run_installer(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not start the installer: {exc}")
            return
        with_quiet(self.worker.browser.quit)
        os._exit(0)  # leave now so the installer can replace our files; it restarts the app when done

    # ------------------------------------------------------------ exit
    def on_close(self):
        self.worker.shutdown()
        self.root.after(300, self.root.destroy)


def with_quiet(fn):
    try:
        fn()
    except Exception:
        pass


def single_instance():
    """True if no other SALTO Buddy is running (they would fight over the Firefox profile)."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\SALTO_Buddy_single_instance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    with_quiet(lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1))  # crisp text on scaled screens
    if not single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, f"{APP_NAME} is already open.")
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
