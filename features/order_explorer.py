"""Order explorer: open a GOLD order's STC and dissect everything in it.

Layout (one job per tab): Summary | Devices | People | Case tabs | Sub-cases | Files
"""
import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from salto import capture, config, files
from salto.actions import order_lookup
from salto.case import Options, download_attachments
from salto.export import export_report
from ui import theme as T
from ui.widgets import DetailView, Segmented, StatusCard, Stepper, Table, ThinProgress

from .base import Feature

FILE_COLS = ["Case", "Title", "Category", "Added by", "Date", "Status"]


class OrderExplorer(Feature):
    title = "Order explorer"

    def build(self, parent):
        self.rep = None
        self.extra_shots = []

        # ---- input bar: order + main action left, secondary actions right
        bar = ttk.Frame(parent, style="Card.TFrame")
        bar.pack(fill="x")
        ttk.Label(bar, text="Order #", font=T.F_BOLD).pack(side="left")
        self.order = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.order, width=16, font=(T.FONT, 11))
        e.pack(side="left", padx=(8, 6))
        e.bind("<Return>", lambda _e: self.go())
        e.focus_set()
        self.open_btn = ttk.Button(bar, text="Open order", style="Accent.TButton", command=self.go)
        self.open_btn.pack(side="left")
        self.export_btn = ttk.Button(bar, text="Export to Excel", command=self.export, state="disabled")
        self.export_btn.pack(side="right")
        ttk.Button(bar, text="Open folder", command=self.open_folder).pack(side="right", padx=6)
        self.pick_btn = ttk.Button(bar, text="Capture a part", command=self.pick)
        self.pick_btn.pack(side="right")
        ttk.Button(bar, text="Screenshot", command=self.shot).pack(side="right", padx=6)

        # ---- order header: title, stage bar, a few key numbers
        head = tk.Frame(parent, bg=T.CARD)
        head.pack(fill="x", pady=(12, 0))
        self.title_lbl = tk.Label(head, text="", bg=T.CARD, fg=T.INK, font=T.F_TITLE, anchor="w")
        self.title_lbl.pack(fill="x")
        steps = tk.Frame(head, bg=T.CARD)
        steps.pack(fill="x", pady=(4, 0))
        self.stepper = Stepper(steps)
        self.stepper.pack(side="left")
        self.folder_lbl = tk.Label(steps, text="", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL, cursor="hand2")
        self.folder_lbl.pack(side="right")
        self.folder_lbl.bind("<Button-1>", lambda _e: self.open_folder())
        self.progress = ThinProgress(parent)
        cards = tk.Frame(parent, bg=T.CARD)
        cards.pack(fill="x", pady=(10, 0))
        self.cards = {}
        for i, name in enumerate(["Status", "Current stage", "EQPs", "Scope devices", "Sub-cases", "Attachments"]):
            c = StatusCard(cards, name)
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            cards.grid_columnconfigure(i, weight=1, uniform="cards")
            self.cards[name] = c

        # ---- one tab per job
        self.tabs = ttk.Notebook(parent, style="Inner.TNotebook")
        self.tabs.pack(fill="both", expand=True, pady=(12, 0))
        self.pages = {}
        for name in ["Summary", "Devices", "People", "Case tabs", "Sub-cases", "Files"]:
            f = tk.Frame(self.tabs, bg=T.CARD)
            self.tabs.add(f, text=name)
            self.pages[name] = f
        self._empty_state()

    # ------------------------------------------------------------ empty / helpers
    def _clear(self, page):
        for w in self.pages[page].winfo_children():
            w.destroy()

    def _empty_state(self):
        for name in self.pages:
            self._clear(name)
            d = DetailView(self.pages[name])
            d.pack(fill="both", expand=True)
            d.title("Open an order to start", "Type a GOLD order number above and press Enter. SALTO Buddy opens its "
                                              "STC in SALTO (in the background) and reads every tab and sub-case.")

    def settings_changed(self):
        self.app.worker.submit(lambda b: b.set_visible(self.app.cfg.get("show_browser", False)))

    def _folder(self):
        if self.rep and self.rep.folder:
            return self.rep.folder
        os.makedirs(self.app.cfg["export_dir"], exist_ok=True)
        return self.app.cfg["export_dir"]

    def open_folder(self):
        os.startfile(self._folder())

    # ------------------------------------------------------------ actions
    def go(self):
        ref = self.order.get().strip()
        if not ref or str(self.open_btn.cget("state")) == "disabled":
            return
        cfg = self.app.cfg
        opts = Options(subcases=cfg.get("subcases", True), downloads=cfg.get("downloads", False),
                       tab_screenshots=cfg.get("tab_screenshots", False))
        self.app.log(f"--- Opening {ref} ---")
        self.app.busy(True, f"Opening {ref}...")
        self.progress.pack(fill="x", pady=(8, 0), after=self.title_lbl.master)
        self.progress.start()
        self.title_lbl.configure(text=f"{ref} · reading SALTO...")
        self.run(lambda b: order_lookup(b, ref, cfg["export_dir"], full=True, opts=opts), self.show, self.failed,
                 busy_widgets=(self.open_btn,))

    def _done_busy(self):
        self.app.busy(False)
        self.progress.stop()
        self.progress.pack_forget()

    def failed(self, exc):
        self._done_busy()
        self.title_lbl.configure(text="")
        messagebox.showerror("SALTO Buddy", f"Opening the order failed: {str(exc).splitlines()[0]}\n\n"
                                            "Click 'Show activity' at the bottom for details.")

    def shot(self):
        folder = files.sub(self._folder(), "Screenshots")
        self.app.busy(True, "Taking a screenshot of the whole SALTO page...")
        self.run(lambda b: (b.ensure_logged_in(), capture.screenshot_screen(b, folder))[1], self._shot_done,
                 lambda _e: self.app.busy(False))

    def pick(self):
        if not self.app.cfg.get("show_browser", False):
            if not messagebox.askyesno("SALTO Buddy", "To capture a part you click on it in Firefox, which is hidden.\n\n"
                                                      "Show the Firefox window now? (You can hide it again in Settings.)"):
                return
            self.app.cfg["show_browser"] = True
            config.save(self.app.cfg)
            self.settings_changed()
            messagebox.showinfo("SALTO Buddy", "Firefox will open. Open the order again if needed, then click "
                                               "'Capture a part'.")
            return
        folder = files.sub(self._folder(), "Screenshots")
        self.app.busy(True, "Click what to capture in Firefox (Esc cancels)")
        self.run(lambda b: (b.ensure_logged_in(), capture.pick_and_capture(b, folder, log=self.app.log))[1],
                 self._shot_done, lambda _e: self.app.busy(False))

    def _shot_done(self, path):
        self.app.busy(False)
        if not path:
            return
        self.extra_shots.append(path)
        self.app.log(f"Saved {path}")
        if self.rep:
            self._files_page()
        if messagebox.askyesno("SALTO Buddy", f"Saved to {path}\n\nOpen it now?"):
            os.startfile(path)

    def export(self):
        if not self.rep:
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                            initialdir=self._folder(), initialfile=f"{self.rep.order_ref}.xlsx")
        if path:
            export_report(self.rep, path)
            self.app.log(f"Saved {path}")
            if messagebox.askyesno("SALTO Buddy", f"Saved to {path}\n\nOpen it now?"):
                os.startfile(path)

    # ------------------------------------------------------------ results
    def show(self, rep):
        self._done_busy()
        self.rep = rep
        case = rep.case
        customer = ""
        if case:
            for td in case.tabs.values():
                for _, fs in td.sections:
                    customer = customer or dict(fs).get("Customer name", "")
        self.title_lbl.configure(text="  ·  ".join(x for x in (rep.order_ref, rep.stc_id or "no STC found",
                                                                case.title if case else "", customer) if x))
        self.export_btn.configure(state="normal" if rep.stc_id else "disabled")
        self.folder_lbl.configure(text=f"Files: {rep.folder}" if rep.folder else "")
        self.stepper.set(rep.stages)
        atts = self._attachments()
        self.cards["Status"].set(rep.status or ("Not found" if not rep.stc_id else ""), None if rep.stc_id else "red")
        self.cards["Current stage"].set(rep.current_stage, "blue" if rep.current_stage else None)
        self.cards["EQPs"].set(str(len(rep.eqps)))
        self.cards["Scope devices"].set(str(len(case.scope_devices)) if case else "—")
        self.cards["Sub-cases"].set(str(len(case.subcases)) if case else "—")
        self.cards["Attachments"].set(str(len(atts)) if case else "—")
        if not case:
            self._empty_state()
            return
        self._summary_page()
        self._devices_page()
        self._people_page()
        self._case_tabs_page()
        self._subcases_page()
        self._files_page()
        self.tabs.select(0)
        errors = [e for c in case.walk() for e in c.errors]
        if errors:
            self.app.log("Could not read: " + "; ".join(errors))

    def _attachments(self):
        if not self.rep or not self.rep.case:
            return []
        out = []
        for c in self.rep.case.walk():
            for i, a in enumerate(c.attachments):
                a.setdefault("_case", c.stc_id)
                a.setdefault("_index", i)
                out.append(a)
        return out

    # ---- Summary
    def _summary_page(self):
        rep, case = self.rep, self.rep.case
        self._clear("Summary")
        d = DetailView(self.pages["Summary"])
        d.pack(fill="both", expand=True)
        d.title(f"{rep.order_ref} · {rep.stc_id}", f"{case.title} · read {datetime.now():%d-%b-%Y %H:%M}")
        d.section("Order")
        d.fields([("Status", rep.status), ("Current stage", rep.current_stage)] + case.header
                 + [("EQPs", ", ".join(rep.eqps) or "none")])
        d.section("Scope of work")
        for n in case.scope:
            d.fields([(f"{n.node}", "   ".join(f"{k.replace('Number of Devices to be ', '').capitalize()}: {v}"
                                               for k, v in n.counts) or "—")])
        d.fields([("Devices in scope", str(len(case.scope_devices))), ("Devices on site", str(len(case.all_devices)))])
        d.section("People")
        d.fields([(p.role or p.party, p.name) for p in case.participants])
        if case.subcases:
            d.section("Sub-cases")
            d.fields([(sc.stc_id, f"{sc.title} — {_stage_text(sc) or '—'}") for sc in case.subcases])
        d.section("Search results")
        d.note(f"STC Search found {len(rep.rows)} row(s) for {rep.order_ref}; SALTO Buddy opened {rep.stc_id}.")

    # ---- Devices
    def _devices_page(self):
        case = self.rep.case
        self._clear("Devices")
        page = self.pages["Devices"]
        top = tk.Frame(page, bg=T.CARD)
        top.pack(fill="x", pady=(10, 6), padx=10)
        holder = tk.Frame(page, bg=T.CARD)
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        def render(choice):
            for w in holder.winfo_children():
                w.destroy()
            scope = choice.startswith("Scope")
            rows, headers = [], []
            for n in case.scope:
                g = n.devices if scope else n.all_devices
                if g:
                    headers = headers or g.headers
                    rows += g.rows
            if not rows:
                tk.Label(holder, text="No devices.", bg=T.CARD, fg=T.MUTED, font=T.F_BODY).pack(anchor="w")
                return
            Table(holder, headers, rows, height=20).pack(fill="both", expand=True)

        Segmented(top, [f"Scope of work ({len(case.scope_devices)})", f"All devices ({len(case.all_devices)})"],
                  render).pack(side="left")
        counts = "   ".join(f"{k.replace('Number of Devices to be ', '').capitalize()}: {v}"
                           for n in case.scope for k, v in n.counts)
        tk.Label(top, text=counts, bg=T.CARD, fg=T.MUTED, font=T.F_SMALL).pack(side="left", padx=14)
        render("Scope")

    # ---- People
    def _people_page(self):
        case = self.rep.case
        self._clear("People")
        rows, seen = [], set()
        for c in case.walk():
            for p in c.participants:
                if (p.name, p.role) not in seen:
                    seen.add((p.name, p.role))
                    rows.append({"Name": p.name, "Role": p.role or p.party, "Case": f"{c.stc_id} · {c.title}"})
        f = tk.Frame(self.pages["People"], bg=T.CARD)
        f.pack(fill="both", expand=True, padx=10, pady=10)
        Table(f, ["Name", "Role", "Case"], rows, height=20).pack(fill="both", expand=True)

    # ---- Case tabs (main case): list of its SALTO tabs | detail
    def _case_tabs_page(self):
        self._clear("Case tabs")
        self._case_browser(self.pages["Case tabs"], self.rep.case)

    def _case_browser(self, parent, c):
        """Tab buttons of one case on top, the selected tab's content below."""
        top = tk.Frame(parent, bg=T.CARD)
        top.pack(fill="x", padx=10, pady=(10, 4))
        detail = DetailView(parent)
        detail.pack(fill="both", expand=True)

        def render(name):
            detail.clear()
            if name == "Stages & people":
                detail.title(f"{c.stc_id} · {c.title}", _stage_text(c))
                if c.stages:
                    detail.section("Stages")
                    detail.fields([(s.name, s.state) for s in c.stages])
                if c.header:
                    detail.section("Case")
                    detail.fields(c.header)
                if c.participants:
                    detail.section("People")
                    detail.fields([(p.role or p.party, p.name) for p in c.participants])
                for e in c.errors:
                    detail.note("Could not read: " + e)
                return
            td = c.tabs[name]
            detail.title(name, f"{c.stc_id} · {c.title}")
            if not td.sections and not td.grids:
                detail.note("SALTO shows nothing in this tab.")
            for sec, fs in td.sections:
                detail.section(sec.title() if sec.isupper() else sec)
                detail.fields(fs)
            for g in td.grids:
                detail.section(f"{g.name if g.name and g.name != 'General' else name} ({len(g.rows)})")
                detail.table(g.headers, g.rows)

        names = ["Stages & people"] + list(c.tabs)
        Segmented(top, names, render).pack(side="left")
        render(names[0])

    # ---- Sub-cases: list | that sub-case's tabs
    def _subcases_page(self):
        case = self.rep.case
        self._clear("Sub-cases")
        page = self.pages["Sub-cases"]
        if not case.subcases:
            d = DetailView(page)
            d.pack(fill="both", expand=True)
            d.title("No sub-cases", "Either the case has none or 'Open every sub-case' is off in Settings.")
            return
        body = ttk.PanedWindow(page, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=10)
        left = tk.Frame(body, bg=T.ZEBRA, highlightthickness=1, highlightbackground=T.LINE)
        nav = ttk.Treeview(left, show="tree", style="Nav.Treeview", selectmode="browse")
        nav.column("#0", width=260)
        nav.pack(fill="both", expand=True, padx=4, pady=4)
        right = tk.Frame(body, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE)
        body.add(left, weight=1)
        body.add(right, weight=4)
        for i, sc in enumerate(case.subcases):
            nav.insert("", "end", iid=str(i), text=f"{sc.stc_id} · {sc.title}   {_stage_text(sc)}")

        def pick(_e=None):
            sel = nav.selection()
            if not sel:
                return
            for w in right.winfo_children():
                w.destroy()
            self._case_browser(right, case.subcases[int(sel[0])])

        nav.bind("<<TreeviewSelect>>", pick)
        nav.selection_set("0")

    # ---- Files: attachments (download on demand) + screenshots
    def _files_page(self):
        self._clear("Files")
        atts = self._attachments()
        split = ttk.PanedWindow(self.pages["Files"], orient="vertical")  # drag the divider to resize
        split.pack(fill="both", expand=True, padx=10, pady=10)
        page = tk.Frame(split, bg=T.CARD)
        lower = tk.Frame(split, bg=T.CARD)
        split.add(page, weight=3)
        split.add(lower, weight=1)
        top = tk.Frame(page, bg=T.CARD)
        top.pack(fill="x", pady=(0, 2))
        tk.Label(top, text=f"Attachments ({len(atts)})", bg=T.CARD, fg=T.ORANGE, font=T.F_SECTION).pack(side="left")
        ttk.Button(top, text="Open folder",
                   command=lambda: os.startfile(files.sub(self._folder(), "Downloads"))).pack(side="right")
        ttk.Button(top, text="Download all", command=lambda: self._download(atts)).pack(side="right", padx=6)
        ttk.Button(top, text="Download selected", style="Accent.TButton",
                   command=lambda: self._download([self._att_of[i] for i in tbl.tv.selection()])).pack(side="right")
        tk.Label(page, text="Select rows (Ctrl/Shift+click), then download. Double-click opens a downloaded file.",
                 bg=T.CARD, fg=T.MUTED, font=T.F_SMALL, anchor="w").pack(fill="x", pady=(0, 6))

        shots = self._screens()
        tk.Label(lower, text=f"Screenshots ({len(shots)})  ·  double-click to open", bg=T.CARD, fg=T.ORANGE,
                 font=T.F_SECTION, anchor="w").pack(fill="x", pady=(8, 4))
        Table(lower, ["Screenshot", "Path"], [[os.path.basename(p), p] for p in shots], height=4).pack(fill="both", expand=True)
        rows = []
        for a in atts:
            saved = a.get("Saved as", "")
            status = "Downloaded" if saved and os.path.exists(saved) else (saved if saved.startswith("failed") else "")
            rows.append({"Case": a["_case"], "Title": a.get("Title") or f"({a.get('Category', 'Attachment')})",
                         "Category": a.get("Category", ""), "Added by": a.get("Added by", ""), "Date": a.get("Date", ""),
                         "Status": status or "Not downloaded", "Path": saved if status == "Downloaded" else ""})
        tbl = Table(page, FILE_COLS, rows, height=10)
        tbl.headers = FILE_COLS
        tbl.tv.configure(selectmode="extended")
        tbl.pack(fill="both", expand=True)
        # map table rows to attachments by item id (stays right after the user sorts the table)
        ids = tbl.tv.get_children()
        self._att_of = dict(zip(ids, atts))
        self._path_of = dict(zip(ids, [r["Path"] for r in rows]))
        tbl.tv.bind("<Double-1>", lambda e: self._open_att(tbl))

    def _open_att(self, tbl):
        sel = tbl.tv.selection()
        if sel:
            p = self._path_of.get(sel[0], "")
            if p and os.path.exists(p):
                os.startfile(p)

    def _download(self, rows):
        rows = [r for r in rows if not (r.get("Saved as") and os.path.exists(r["Saved as"]))]
        if not rows:
            messagebox.showinfo("SALTO Buddy", "Nothing new to download: select rows that are not downloaded yet.")
            return
        rep = self.rep
        self.app.busy(True, f"Downloading {len(rows)} file(s)...")
        self.progress.pack(fill="x", pady=(8, 0), after=self.title_lbl.master)
        self.progress.start()

        def done(_r):
            self._done_busy()
            self._files_page()
            ok = sum(1 for r in rows if r.get("Saved as") and os.path.exists(r["Saved as"]))
            self.cards["Attachments"].set(str(len(self._attachments())))
            self.app.log(f"Downloaded {ok} of {len(rows)} file(s) to {os.path.join(rep.folder, 'Downloads')}")
            if ok and messagebox.askyesno("SALTO Buddy", f"Downloaded {ok} of {len(rows)} file(s).\n\nOpen the folder?"):
                os.startfile(os.path.join(rep.folder, "Downloads"))

        def work(b):
            b.ensure_logged_in()
            return download_attachments(b, rep.stc_id, rows, rep.folder, log=self.app.log)

        self.run(work, done, lambda _e: (self._done_busy(), self._files_page()))

    def _screens(self):
        shots = list(self.extra_shots)
        if self.rep and self.rep.case:
            shots += [s for c in self.rep.case.walk() for s in c.screenshots]
        folder = os.path.join(self.rep.folder, "Screenshots") if self.rep and self.rep.folder else ""
        if folder and os.path.isdir(folder):
            shots += [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".png")]
        return sorted(set(shots))


def _stage_text(c):
    cur = [s.name for s in c.stages if s.state == "current"]
    if cur:
        return f"stage: {cur[0]}"
    if c.stages and all(s.state == "completed" for s in c.stages):
        return "completed"
    return ""
