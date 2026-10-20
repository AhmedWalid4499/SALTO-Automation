"""SALTO Buddy - desktop app.

Run from source:  py app.py
"""
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from features import FEATURES
from salto import config, updater
from salto.version import APP_NAME, __version__
from salto.worker import BrowserWorker
from ui import theme as T

STATES = {  # browser state -> (dot colour, text)
    "offline": ("#6B7280", "SALTO: not connected"),
    "starting": ("#F59E0B", "Starting Firefox..."),
    "signing-in": ("#F59E0B", "Signing in to SALTO..."),
    "connected": ("#22C55E", "SALTO: connected"),
}


class App:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.cfg = config.load()
        self._ui_q = queue.Queue()
        self._log_lines = []
        self._log_win = None
        self._update = None
        self.on_log = []  # features subscribe to see progress lines

        root.title(APP_NAME)
        root.geometry("1280x800")
        root.minsize(1000, 640)
        root.after(0, lambda: root.state("zoomed"))  # fit whatever screen/scaling the user has
        root.configure(fg_color=T.BG)
        ico = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets", "app.ico")
        if os.path.exists(ico):
            root.after(200, lambda: root.iconbitmap(ico))  # CTk resets the icon on start

        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)
        self._sidebar()
        self.main = ctk.CTkFrame(root, fg_color=T.BG, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")

        self.worker = BrowserWorker(log=self.log, on_state=lambda s: self.ui(lambda: self._set_state(s)))
        self.pages = {}
        for cls in FEATURES:
            page = ctk.CTkFrame(self.main, fg_color=T.BG, corner_radius=0)
            cls(self).build(page)
            self.pages[cls.title] = page
            self._nav_button(cls.title)
        self.show_page(FEATURES[0].title)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._pump)
        if self.cfg.get("check_updates_on_start", True):
            root.after(1500, lambda: self.check_updates(silent=True))

    # ------------------------------------------------------------ sidebar
    def _sidebar(self):
        sb = ctk.CTkFrame(self.root, width=230, fg_color=T.SIDEBAR, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.pack_propagate(False)
        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(22, 26))
        ctk.CTkLabel(brand, text="S", width=38, height=38, corner_radius=10, fg_color=T.ORANGE,
                     text_color="white", font=T.font(20, "bold")).pack(side="left")
        ctk.CTkLabel(brand, text="  SALTO Buddy", text_color="white", font=T.font(18, "bold")).pack(side="left")
        ctk.CTkLabel(sb, text="TOOLS", text_color="#6B7280", font=T.font(10, "bold")).pack(anchor="w", padx=22)
        self.nav = ctk.CTkFrame(sb, fg_color="transparent")
        self.nav.pack(fill="x", padx=10, pady=(6, 0))
        self.nav_buttons = {}

        bottom = ctk.CTkFrame(sb, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=10, pady=14)
        self.update_btn = ctk.CTkButton(bottom, text="⬆  Update available", fg_color=T.ORANGE, hover_color=T.ORANGE_HOVER,
                                        text_color="white", font=T.font(13, "bold"), height=38, corner_radius=8,
                                        command=self.prompt_update)
        st = ctk.CTkFrame(bottom, fg_color="transparent")
        st.pack(fill="x", padx=8, pady=(4, 8))
        self.state_dot = ctk.CTkLabel(st, text="●", text_color=STATES["offline"][0], font=T.font(14))
        self.state_dot.pack(side="left")
        self.state_lbl = ctk.CTkLabel(st, text=STATES["offline"][1], text_color=T.SIDEBAR_TEXT, font=T.font(12))
        self.state_lbl.pack(side="left", padx=6)
        for text, cmd in (("Open SALTO", self.login), ("Close browser", self.close_browser),
                          ("Activity log", self.show_log), ("Settings", self.show_settings)):
            self._side_button(bottom, text, cmd).pack(fill="x", pady=1)

    def _side_button(self, parent, text, cmd):
        return ctk.CTkButton(parent, text=text, anchor="w", fg_color="transparent", hover_color=T.SIDEBAR_HOVER,
                             text_color=T.SIDEBAR_TEXT, font=T.font(13), height=34, corner_radius=8, command=cmd)

    def _nav_button(self, title):
        b = ctk.CTkButton(self.nav, text=f"  {title}", anchor="w", fg_color="transparent", hover_color=T.SIDEBAR_HOVER,
                          text_color=T.SIDEBAR_TEXT, font=T.font(14), height=40, corner_radius=8,
                          command=lambda: self.show_page(title))
        b.pack(fill="x", pady=2)
        self.nav_buttons[title] = b

    def show_page(self, title):
        for t, p in self.pages.items():
            p.pack_forget()
            self.nav_buttons[t].configure(fg_color="transparent", text_color=T.SIDEBAR_TEXT)
        self.pages[title].pack(fill="both", expand=True)
        self.nav_buttons[title].configure(fg_color=T.SIDEBAR_HOVER, text_color="white")

    def _set_state(self, s):
        color, text = STATES.get(s, STATES["offline"])
        self.state_dot.configure(text_color=color)
        self.state_lbl.configure(text=text)

    # ------------------------------------------------------------ thread-safe GUI access
    def ui(self, fn):
        self._ui_q.put(fn)

    def _pump(self):
        while not self._ui_q.empty():
            self._ui_q.get()()
        self.root.after(80, self._pump)

    def log(self, msg):
        line = f"[{datetime.now():%H:%M:%S}] {msg}"

        def write():
            self._log_lines.append(line)
            for cb in self.on_log:
                cb(msg)
            if self._log_win and self._log_win.winfo_exists():
                self._log_box.configure(state="normal")
                self._log_box.insert("end", line + "\n")
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
        self.ui(write)

    def show_log(self):
        if self._log_win and self._log_win.winfo_exists():
            self._log_win.focus()
            return
        w = ctk.CTkToplevel(self.root)
        w.title(f"{APP_NAME} - Activity log")
        w.geometry("820x420")
        w.configure(fg_color=T.BG)
        box = ctk.CTkTextbox(w, font=ctk.CTkFont(family="Consolas", size=12), fg_color=T.CARD,
                             border_width=1, border_color=T.BORDER, corner_radius=8)
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("end", "\n".join(self._log_lines) + ("\n" if self._log_lines else ""))
        box.see("end")
        box.configure(state="disabled")
        self._log_win, self._log_box = w, box
        w.after(150, w.lift)

    # ------------------------------------------------------------ settings
    def show_settings(self):
        w = ctk.CTkToplevel(self.root)
        w.title(f"{APP_NAME} - Settings")
        w.geometry("560x330")
        w.resizable(False, False)
        w.configure(fg_color=T.BG)
        w.after(150, w.lift)
        c = ctk.CTkFrame(w, fg_color=T.CARD, corner_radius=12, border_width=1, border_color=T.BORDER)
        c.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(c, text="Settings", font=T.font(18, "bold"), text_color=T.INK).pack(anchor="w", padx=20, pady=(16, 10))

        ctk.CTkLabel(c, text="Export folder", font=T.font(12, "bold"), text_color=T.MUTED).pack(anchor="w", padx=20)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(2, 12))
        folder = ctk.CTkEntry(row, height=34)
        folder.insert(0, self.cfg["export_dir"])
        folder.pack(side="left", fill="x", expand=True)

        def browse():
            v = filedialog.askdirectory(initialdir=self.cfg["export_dir"], parent=w)
            if v:
                folder.delete(0, "end")
                folder.insert(0, v)
        ctk.CTkButton(row, text="Browse", width=90, height=34, fg_color="#F3F4F6", text_color=T.INK,
                      hover_color=T.GREY, command=browse).pack(side="left", padx=(8, 0))

        auto = ctk.CTkSwitch(c, text="Check for updates when SALTO Buddy starts", progress_color=T.ORANGE,
                             font=T.font(13), text_color=T.INK)
        if self.cfg.get("check_updates_on_start", True):
            auto.select()
        auto.pack(anchor="w", padx=20, pady=4)

        foot = ctk.CTkFrame(c, fg_color="transparent")
        foot.pack(fill="x", side="bottom", padx=20, pady=16)
        ctk.CTkLabel(foot, text=f"Version {__version__}", text_color=T.MUTED, font=T.font(12)).pack(side="left")
        ctk.CTkButton(foot, text="Check for updates", width=150, height=34, fg_color="#F3F4F6", text_color=T.INK,
                      hover_color=T.GREY, command=lambda: self.check_updates(silent=False)).pack(side="left", padx=12)

        def save():
            self.cfg["export_dir"] = folder.get().strip() or config.DEFAULTS["export_dir"]
            self.cfg["check_updates_on_start"] = bool(auto.get())
            config.save(self.cfg)
            w.destroy()
        ctk.CTkButton(foot, text="Save", width=100, height=34, fg_color=T.ORANGE, hover_color=T.ORANGE_HOVER,
                      command=save).pack(side="right")

    # ------------------------------------------------------------ updates (GitHub releases)
    def check_updates(self, silent):
        def work():
            try:
                info = updater.check()
            except Exception as exc:
                self.log(f"Update check failed: {exc}")
                if not silent:
                    self.ui(lambda: messagebox.showwarning(APP_NAME, f"Could not reach GitHub to check for updates.\n\n{exc}"))
                return
            self.ui(lambda: self._on_update(info, silent))
        threading.Thread(target=work, daemon=True).start()

    def _on_update(self, info, silent):
        self._update = info
        if not info:
            if not silent:
                messagebox.showinfo(APP_NAME, f"You're up to date (version {__version__}).")
            return
        self.update_btn.configure(text=f"⬆  Update available  ({info.version})")
        self.update_btn.pack(fill="x", pady=(0, 10), before=self.update_btn.master.winfo_children()[1])
        self.log(f"Update available: {info.version}")
        if not silent or self.cfg.get("skipped_version") != info.version:
            self.prompt_update()

    def prompt_update(self):
        info = self._update
        if not info:
            return
        w = ctk.CTkToplevel(self.root)
        w.title(f"{APP_NAME} - Update available")
        w.geometry("520x380")
        w.resizable(False, False)
        w.configure(fg_color=T.BG)
        w.transient(self.root)
        w.after(150, w.lift)
        c = ctk.CTkFrame(w, fg_color=T.CARD, corner_radius=12, border_width=1, border_color=T.BORDER)
        c.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(c, text="Update available", font=T.font(20, "bold"), text_color=T.INK).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(c, text=f"Version {info.version} is ready to download (you have {__version__}).",
                     font=T.font(13), text_color=T.MUTED).pack(anchor="w", padx=20)
        notes = ctk.CTkTextbox(c, height=120, fg_color="#F9FAFB", border_width=1, border_color=T.BORDER, font=T.font(12))
        notes.insert("end", info.notes or "No release notes.")
        notes.configure(state="disabled")
        notes.pack(fill="x", padx=20, pady=12)
        bar = ctk.CTkProgressBar(c, progress_color=T.ORANGE)
        bar.set(0)
        status = ctk.CTkLabel(c, text="", font=T.font(12), text_color=T.MUTED)
        foot = ctk.CTkFrame(c, fg_color="transparent")
        foot.pack(fill="x", side="bottom", padx=20, pady=16)

        def later():
            self.cfg["skipped_version"] = info.version
            config.save(self.cfg)
            w.destroy()

        def go():
            if not updater.frozen():
                messagebox.showinfo(APP_NAME, "Running from source: pull the latest code from GitHub instead.", parent=w)
                return
            dl.configure(state="disabled", text="Downloading...")
            bar.pack(fill="x", padx=20)
            status.pack(anchor="w", padx=20, pady=4)

            def progress(done, total):
                self.ui(lambda: (bar.set(done / total if total else 0),
                                 status.configure(text=f"{done / 1e6:.1f} MB of {total / 1e6:.1f} MB")))

            def work():
                try:
                    path = updater.download(info, progress)
                except Exception as exc:
                    self.ui(lambda: (messagebox.showerror(APP_NAME, f"Download failed:\n{exc}", parent=w),
                                     dl.configure(state="normal", text="Download and install")))
                    return
                self.ui(lambda: self._install(path))
            threading.Thread(target=work, daemon=True).start()

        dl = ctk.CTkButton(foot, text="Download and install", height=36, fg_color=T.ORANGE, hover_color=T.ORANGE_HOVER,
                           font=T.font(13, "bold"), command=go)
        dl.pack(side="right")
        ctk.CTkButton(foot, text="Later", width=90, height=36, fg_color="#F3F4F6", text_color=T.INK, hover_color=T.GREY,
                      command=later).pack(side="right", padx=8)
        if info.page:
            ctk.CTkButton(foot, text="Release page", width=110, height=36, fg_color="transparent", text_color=T.MUTED,
                          hover_color="#F3F4F6", command=lambda: os.startfile(info.page)).pack(side="left")

    def _install(self, path):
        try:
            updater.run_installer(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not start the installer:\n{exc}")
            return
        # leave immediately so the installer can replace our files; it restarts the app when done
        self.worker.browser.quit()
        os._exit(0)

    # ------------------------------------------------------------ browser
    def login(self):
        self.worker.submit(lambda b: b.ensure_logged_in())

    def close_browser(self):
        self.worker.submit(lambda b: b.quit())

    def on_close(self):
        self.worker.shutdown()
        self.root.after(300, self.root.destroy)


def main():
    root = ctk.CTk()
    T.setup(root)  # after the root exists: ttk.Style() would otherwise create a second Tk root
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
