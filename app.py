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
from tkinter import filedialog, messagebox, ttk

from features import FEATURES
from salto import config, errors, keystore, updater
from salto.version import APP_NAME, __version__
from salto.worker import BrowserWorker
from ui import guide
from ui import theme as T
from ui.widgets import Pill

PILL = {  # browser state -> (text, dot colour)
    "offline": ("Ready", T.PILL_READY),
    "starting": ("Starting Firefox...", T.ORANGE),
    "signing-in": ("Signing in to SALTO...", T.ORANGE),
    "connected": ("Connected to SALTO", T.PILL_READY),
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

        self._header()
        tk.Frame(root, bg=T.ORANGE, height=3).pack(fill="x")
        self._statusbar()
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(4, 0))

        self.worker = BrowserWorker(log=self.log, on_state=lambda s: self.ui(lambda: self._set_state(s)),
                                    visible=self.cfg.get("show_browser", False))
        self.reports = {}      # order_ref -> OrderReport read this session (shared by the features)
        self.explorer = None   # the Order explorer feature (Ask Buddy opens orders through it)
        self.features = []
        for cls in FEATURES:
            page = ttk.Frame(self.tabs, style="Card.TFrame", padding=(16, 12))
            self.tabs.add(page, text=cls.title)
            f = cls(self)
            if cls.__name__ == "OrderExplorer":
                self.explorer = f
            f.build(page)
            self.features.append(f)

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
                    self.log(f"Ask Buddy: found the team key in {folder}", quiet=True)
                    for feat in self.features:
                        getattr(feat, "key_changed", lambda: None)()
                self.ui(found)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ chrome
    def _header(self):
        h = tk.Frame(self.root, bg=T.HEADER, height=58)
        h.pack(fill="x")
        h.pack_propagate(False)
        logo = tk.Label(h, text="SB", bg=T.ORANGE, fg="white", font=(T.FONT, 12, "bold"), width=3)
        logo.pack(side="left", padx=(16, 10), pady=12, ipady=4)
        txt = tk.Frame(h, bg=T.HEADER)
        txt.pack(side="left")
        tk.Label(txt, text=APP_NAME, bg=T.HEADER, fg="white", font=T.F_APP).pack(anchor="w")
        tk.Label(txt, text="SALTO order explorer", bg=T.HEADER, fg=T.SUBTLE, font=T.F_SMALL).pack(anchor="w")
        self.update_btn = ttk.Button(h, text="Check for updates", style="Header.TButton",
                                     command=lambda: self.prompt_update() if self._update else self.check_updates(False))
        self.update_btn.pack(side="right", padx=(6, 16))
        ttk.Button(h, text="Settings", style="Header.TButton", command=self.show_settings).pack(side="right")
        ttk.Button(h, text="Guide", style="Header.TButton", command=lambda: guide.show_guide(self.root)).pack(
            side="right", padx=6)
        self.pill = Pill(h)
        self.pill.pack(side="right", padx=12)

    def _statusbar(self):
        bar = tk.Frame(self.root, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE)
        bar.pack(side="bottom", fill="x")
        top = tk.Frame(bar, bg=T.CARD)
        top.pack(fill="x")
        self.status = tk.Label(top, text="Ready", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL, anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=12, pady=4)
        self.log_link = tk.Label(top, text="Show activity", bg=T.CARD, fg=T.ORANGE, font=T.F_SMALL_BOLD, cursor="hand2")
        self.log_link.pack(side="right", padx=12)
        self.log_link.bind("<Button-1>", lambda e: self.toggle_log())
        self.logbox = tk.Text(bar, height=7, font=T.F_LOG, bg=T.CARD, fg=T.INK, borderwidth=0,
                              highlightthickness=0, padx=12, state="disabled")

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
        w = self._dialog("Settings", 560)
        f = ttk.Frame(w, style="Card.TFrame", padding=(20, 16))
        f.pack(fill="both", expand=True)
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
                                       ("check_updates_on_start", "Check for updates when SALTO Buddy starts")]):
            opts[k] = tk.BooleanVar(value=self.cfg.get(k, config.DEFAULTS.get(k, True)))
            ttk.Checkbutton(f, text=text, variable=opts[k]).grid(row=4 + i, column=0, columnspan=3, sticky="w", pady=2)
        f.columnconfigure(0, weight=1)

        # Ask Buddy: Claude API key, stored encrypted for this Windows user (DPAPI)
        ttk.Label(f, text="Ask Buddy", style="Section.TLabel").grid(row=10, column=0, columnspan=3, sticky="w", pady=(16, 4))
        ttk.Label(f, text="Claude API key (from console.anthropic.com). Questions and the order data they need are "
                          "sent to Anthropic.", style="Muted.TLabel", wraplength=500).grid(row=11, column=0, columnspan=3,
                                                                                           sticky="w")
        has_key = bool(keystore.unprotect(self.cfg.get("claude_key", "")))
        key = tk.StringVar()
        key_entry = ttk.Entry(f, textvariable=key, show="•", width=52)
        key_entry.grid(row=12, column=0, sticky="ew", pady=(4, 0))
        if has_key:
            key_entry.insert(0, "(saved - type a new key to replace it)")
            key_entry.configure(show="")
            key_entry.bind("<FocusIn>", lambda e: (key.set("") if key.get().startswith("(saved") else None,
                                                   key_entry.configure(show="•")))
        key_state = ttk.Label(f, text="Key saved" if has_key else "No key yet", style="Muted.TLabel")
        key_state.grid(row=13, column=0, columnspan=3, sticky="w")

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
        ttk.Button(f, text="Test", command=test_key).grid(row=12, column=1, padx=6, pady=(4, 0))
        ttk.Button(f, text="Remove", command=lambda: (key.set(""), self.cfg.update(claude_key=""),
                                                     key_state.configure(text="Key removed"))).grid(row=12, column=2,
                                                                                                     pady=(4, 0))

        # team key: one file in a team-only folder, read by everyone's SALTO Buddy
        ttk.Label(f, text="Team key folder (only Orange staff can open it). Leave your own key empty to use the "
                          "team key.", style="Muted.TLabel", wraplength=500).grid(row=14, column=0, columnspan=3,
                                                                                  sticky="w", pady=(10, 0))
        team_dir = tk.StringVar(value=os.path.expandvars(self.cfg.get("team_key_dir") or config.TEAM_KEY_DIR))
        ttk.Entry(f, textvariable=team_dir, width=52).grid(row=15, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(f, text="Browse", command=lambda: team_dir.set(
            filedialog.askdirectory(initialdir=team_dir.get() or None, parent=w) or team_dir.get())).grid(
            row=15, column=1, padx=6, pady=(4, 0))
        team_state = ttk.Label(f, text="", style="Muted.TLabel")
        team_state.grid(row=16, column=0, columnspan=3, sticky="w")

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
        ttk.Button(f, text="Save as team key", command=save_team_key).grid(row=15, column=2, pady=(4, 0))

        foot = ttk.Frame(f, style="Card.TFrame")
        foot.grid(row=20, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        ttk.Label(foot, text=f"Version {__version__}  ·  © 2026 Ahmed Walid", style="Muted.TLabel").pack(side="left")

        def save():
            self.cfg["export_dir"] = folder.get().strip() or config.DEFAULTS["export_dir"]
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
        ttk.Button(foot, text="Done", style="Accent.TButton", command=save).pack(side="right")

    def _dialog(self, title, width):
        w = tk.Toplevel(self.root)
        w.title(f"{APP_NAME} - {title}")
        w.configure(bg=T.CARD)
        w.transient(self.root)
        w.resizable(False, False)
        w.bind("<Escape>", lambda e: w.destroy())
        w.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + 80
        w.geometry(f"+{max(0, x)}+{max(0, y)}")
        w.grab_set()
        return w

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
        self.update_btn.configure(text=f"Update to {info.version}", style="Update.TButton")
        self.log(f"Update available: {info.version}")
        if not silent or self.cfg.get("skipped_version") != info.version:
            self.prompt_update()

    def prompt_update(self):
        info = self._update
        if not info:
            return
        w = self._dialog("Update available", 520)
        f = ttk.Frame(w, style="Card.TFrame", padding=(20, 16))
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"SALTO Buddy {info.version} is available", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text=f"You have {__version__}. What's new:", style="Muted.TLabel").pack(anchor="w", pady=(2, 6))
        notes = tk.Text(f, height=8, width=60, wrap="word", font=T.F_BODY, bg=T.ZEBRA, borderwidth=0,
                        highlightthickness=1, highlightbackground=T.LINE, padx=8, pady=6)
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
