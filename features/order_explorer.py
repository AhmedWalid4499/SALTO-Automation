"""Order explorer: open a GOLD order's STC and dissect everything in it."""
import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from salto import capture, files
from salto.actions import order_lookup
from salto.case import Options
from salto.export import export_report
from ui import theme as T
from ui.widgets import DetailView, StatusCard, Stepper, ThinProgress

from .base import Feature


class OrderExplorer(Feature):
    title = "Order explorer"

    def build(self, parent):
        self.rep = None
        self.views = {}          # nav item id -> render(detail)
        self.extra_shots = []    # screenshots taken with the buttons

        # ---- input bar
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
        self.head = ttk.Label(bar, text="", style="Title.TLabel")
        self.head.pack(side="left", padx=16)

        # ---- options (left) and actions (right): own row so nothing falls off small screens
        opt = ttk.Frame(parent, style="Card.TFrame")
        opt.pack(fill="x", pady=(8, 0))
        self.opt_vars = {}
        for k, text in [("subcases", "Open every sub-case"),
                        ("downloads", "Download attachments"),
                        ("tab_screenshots", "Screenshot every tab")]:
            v = tk.BooleanVar(value=self.app.cfg.get(k, k != "tab_screenshots"))
            v.trace_add("write", lambda *_a, k=k, v=v: self._save_opt(k, v))
            ttk.Checkbutton(opt, text=text, variable=v).pack(side="left", padx=(0, 14))
            self.opt_vars[k] = v
        self.export_btn = ttk.Button(opt, text="Export to Excel", command=self.export, state="disabled")
        self.export_btn.pack(side="right")
        ttk.Button(opt, text="Open folder", command=self.open_folder).pack(side="right", padx=6)
        ttk.Button(opt, text="Pick & capture", command=self.pick).pack(side="right")
        ttk.Button(opt, text="Screenshot SALTO", command=self.shot).pack(side="right", padx=6)

        # ---- status cards + stepper
        cards = tk.Frame(parent, bg=T.CARD)
        cards.pack(fill="x", pady=(10, 0))
        self.cards = {}
        for i, name in enumerate(["STC", "Status", "Current stage", "EQPs", "Scope devices", "Participants",
                                  "Sub-cases", "Files"]):
            c = StatusCard(cards, name)
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            cards.grid_columnconfigure(i, weight=1, uniform="cards")
            self.cards[name] = c
        steps = tk.Frame(parent, bg=T.CARD)
        steps.pack(fill="x", pady=(8, 0))
        self.stepper = Stepper(steps)
        self.stepper.pack(side="left")
        self.folder_lbl = ttk.Label(steps, text="", style="Muted.TLabel", cursor="hand2")
        self.folder_lbl.pack(side="right")
        self.folder_lbl.bind("<Button-1>", lambda _e: self.open_folder())
        self.stepper_row = steps
        self.progress = ThinProgress(parent)

        # ---- explorer: navigation | detail
        body = ttk.PanedWindow(parent, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(10, 0))
        left = tk.Frame(body, bg=T.ZEBRA, highlightthickness=1, highlightbackground=T.LINE)
        tk.Label(left, text="ORDER", bg=T.ZEBRA, fg=T.MUTED, font=T.F_CAPS, anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        self.nav = ttk.Treeview(left, show="tree", style="Nav.Treeview", selectmode="browse")
        self.nav.column("#0", width=230)
        ns = ttk.Scrollbar(left, orient="vertical", command=self.nav.yview)
        self.nav.configure(yscrollcommand=ns.set)
        ns.pack(side="right", fill="y")
        self.nav.pack(fill="both", expand=True, padx=(4, 0), pady=(0, 4))
        self.nav.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())
        right = tk.Frame(body, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE)
        self.detail = DetailView(right)
        self.detail.pack(fill="both", expand=True)
        body.add(left, weight=1)
        body.add(right, weight=4)
        self.detail.title("Open an order to start",
                          "Type a GOLD order number above and press Enter. SALTO Buddy opens its STC in SALTO "
                          "and reads every tab, sub-case and attachment.")

    # ------------------------------------------------------------ options / folders
    def _save_opt(self, k, v):
        self.app.cfg[k] = bool(v.get())
        from salto import config
        config.save(self.app.cfg)

    def settings_changed(self):
        for k, v in self.opt_vars.items():
            if v.get() != self.app.cfg.get(k, v.get()):
                v.set(self.app.cfg[k])

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
        opts = Options(subcases=self.opt_vars["subcases"].get(), downloads=self.opt_vars["downloads"].get(),
                       tab_screenshots=self.opt_vars["tab_screenshots"].get())
        base = self.app.cfg["export_dir"]
        self.app.log(f"--- Opening {ref} ---")
        self.app.busy(True, f"Opening {ref}...")
        self.progress.pack(fill="x", pady=(6, 0), before=self.stepper_row)
        self.progress.start(12)
        self.head.configure(text=f"{ref} · working...")
        self.run(lambda b: order_lookup(b, ref, base, full=True, opts=opts), self.show, self.failed,
                 busy_widgets=(self.open_btn,))

    def _done_busy(self):
        self.app.busy(False)
        self.progress.stop()
        self.progress.pack_forget()

    def failed(self, exc):
        self._done_busy()
        self.head.configure(text="")
        messagebox.showerror("SALTO Buddy", f"Opening the order failed: {str(exc).splitlines()[0]}\n\n"
                                            "Click 'Show activity' at the bottom for details.")

    def shot(self):
        folder = files.sub(self._folder(), "Screenshots")
        self.app.busy(True, "Taking screenshot...")
        self.run(lambda b: (b.ensure_logged_in(), capture.screenshot_screen(b, folder))[1], self._shot_done,
                 lambda _e: self.app.busy(False))

    def pick(self):
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
            self._fill_nav(keep="screens")
        if messagebox.askyesno("SALTO Buddy", f"Saved to {path}\n\nOpen it now?"):
            os.startfile(path)

    def export(self):
        if not self.rep:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialdir=self._folder(),
            initialfile=f"{self.rep.order_ref}.xlsx")
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
        self.head.configure(text=" · ".join(x for x in (rep.order_ref, rep.stc_id or "no STC found", customer) if x))
        self.export_btn.configure(state="normal" if rep.stc_id else "disabled")
        self.folder_lbl.configure(text=f"Saved in: {rep.folder}" if rep.folder else "")
        cases = list(case.walk()) if case else []
        n_files = sum(1 for c in cases for a in c.attachments if os.path.exists(a.get("Saved as", "")))
        self.cards["STC"].set(rep.stc_id or "Not found", None if rep.stc_id else "red")
        self.cards["Status"].set(rep.status)
        self.cards["Current stage"].set(rep.current_stage, "blue" if rep.current_stage else None)
        self.cards["EQPs"].set(str(len(rep.eqps)))
        self.cards["Scope devices"].set(str(len(case.scope_devices)) if case else "—")
        self.cards["Participants"].set(str(len(case.participants)) if case else "—")
        self.cards["Sub-cases"].set(str(len(case.subcases)) if case else "—")
        self.cards["Files"].set(str(n_files) if case else "—")
        self.stepper.set(rep.stages)
        self._fill_nav()
        errors = [e for c in cases for e in c.errors]
        if errors:
            self.app.log("Could not read: " + "; ".join(errors))

    def _fill_nav(self, keep=None):
        rep, case = self.rep, self.rep.case
        self.nav.delete(*self.nav.get_children())
        self.views = {}

        def add(parent, iid, text, render, open_=False):
            self.nav.insert(parent, "end", iid=iid, text=text, open=open_)
            self.views[iid] = render

        add("", "summary", "Summary", lambda d: self._summary(d))
        if case:
            add("", "scope", f"Scope of work devices ({len(case.scope_devices)})", lambda d: self._devices(d, True))
            add("", "alldev", f"All devices ({len(case.all_devices)})", lambda d: self._devices(d, False))
            add("", "people", f"Participants ({len(case.participants)})", lambda d: self._people(d, case))
            self._add_case("", "main", case, open_=True, add=add)
            if case.subcases:
                add("", "subs", f"Sub-cases ({len(case.subcases)})", lambda d: self._subs(d, case), open_=True)
                for i, sc in enumerate(case.subcases):
                    self._add_case("subs", f"sub{i}", sc, add=add)
            n = sum(1 for c in case.walk() for a in c.attachments)
            add("", "files", f"Downloads ({n})", lambda d: self._downloads(d, case))
        shots = self._screens()
        add("", "screens", f"Screenshots ({len(shots)})", lambda d: self._screens_view(d))
        add("", "search", f"Search results ({len(rep.rows)})", lambda d: self._search(d))
        target = keep if keep in self.views else "summary"
        self.nav.selection_set(target)
        self.nav.see(target)

    def _add_case(self, parent, iid, c, add, open_=False):
        add(parent, iid, f"{c.stc_id} · {c.title}", lambda d, c=c: self._case(d, c), open_)
        for name, td in c.tabs.items():
            add(iid, f"{iid}/{name}", name, lambda d, c=c, td=td: self._tab(d, c, td))

    def _show_selected(self):
        sel = self.nav.selection()
        if sel and sel[0] in self.views:
            self.detail.clear()
            self.views[sel[0]](self.detail)

    # ------------------------------------------------------------ renderers
    def _summary(self, d):
        rep, case = self.rep, self.rep.case
        d.title(f"{rep.order_ref} · {rep.stc_id or 'no STC'}", f"Read {datetime.now():%d-%b-%Y %H:%M}")
        d.section("Order")
        pairs = [("GOLD order", rep.order_ref), ("STC", rep.stc_id), ("Status", rep.status),
                 ("Current stage", rep.current_stage),
                 ("Stages", "  ›  ".join(f"{s.name} ({s.state})" for s in rep.stages)),
                 ("EQPs", ", ".join(rep.eqps) or "none")]
        d.fields(pairs)
        if not case:
            return
        d.fields(case.header)
        d.section("Scope of work")
        for n in case.scope:
            d.fields([(f"{n.product} › {n.node}", "   ".join(f"{k.replace('Number of Devices to be ', '')}: {v}"
                                                             for k, v in n.counts) or "—")])
        d.fields([("Scope of work devices", str(len(case.scope_devices))), ("All devices", str(len(case.all_devices)))])
        d.section("People")
        d.fields([(p.role or p.party, p.name) for p in case.participants])
        if case.subcases:
            d.section("Sub-cases")
            d.fields([(sc.stc_id, f"{sc.title} — {_stage_text(sc)}") for sc in case.subcases])
        if rep.folder:
            d.section("Files")
            d.link(rep.folder, rep.folder)

    def _devices(self, d, scope):
        case = self.rep.case
        d.title("Scope of work devices" if scope else "All devices",
                "TS tab with 'Scope of work only' ticked" if scope else "TS tab, every device on the site")
        if not case.scope:
            d.note("No TS product nodes in this case.")
        for n in case.scope:
            g = n.devices if scope else n.all_devices
            d.section(f"{n.product} › {n.node}")
            if scope and n.counts:
                d.fields([(k.replace("Number of Devices to be ", "Devices ").capitalize(), v) for k, v in n.counts])
            d.table(g.headers, g.rows) if g else d.note("No devices.")

    def _people(self, d, case):
        d.title("Participants", f"{case.stc_id} and its sub-cases")
        seen = set()
        for c in case.walk():
            people = [(p.role or p.party, p.name) for p in c.participants if (p.name, p.role) not in seen]
            seen.update((p.name, p.role) for p in c.participants)
            if people:
                d.section(f"{c.stc_id} · {c.title}")
                d.fields(people)

    def _subs(self, d, case):
        d.title("Sub-cases", "Every case linked in the Overview tree")
        d.table(["Case", "Type", "Stage", "Participants", "Attachments"],
                [[sc.stc_id, sc.title, _stage_text(sc), len(sc.participants), len(sc.attachments)] for sc in case.subcases])

    def _case(self, d, c):
        d.title(f"{c.stc_id} · {c.title}", _stage_text(c))
        if c.stages:
            d.section("Stages")
            d.fields([(s.name, s.state) for s in c.stages])
        if c.header:
            d.section("Case")
            d.fields(c.header)
        if c.participants:
            d.section("Participants")
            d.fields([(p.role or p.party, p.name) for p in c.participants])
        if c.errors:
            d.section("Could not read")
            for e in c.errors:
                d.note(e)

    def _tab(self, d, c, td):
        d.title(td.name, f"{c.stc_id} · {c.title}")
        if not td.sections and not td.grids:
            d.note("SALTO shows nothing in this tab.")
        for sec, fs in td.sections:
            d.section(sec.title() if sec.isupper() else sec)
            d.fields(fs)
        for g in td.grids:
            d.section(f"{g.name if g.name and g.name != 'General' else td.name} ({len(g.rows)})")
            d.table(g.headers, g.rows)

    def _downloads(self, d, case):
        d.title("Downloads", "Double-click a row to open the file")
        rows = []
        for c in case.walk():
            for a in c.attachments:
                saved = a.get("Saved as", "")
                title = a.get("Title") or (os.path.splitext(os.path.basename(saved))[0] if os.path.exists(saved) else "")
                rows.append({"Case": c.stc_id, "Title": title, "Category": a.get("Category", ""),
                             "Added by": a.get("Added by", ""), "Date": a.get("Date", ""), "Saved as": a.get("Saved as", "")})
        d.table(["Case", "Title", "Category", "Added by", "Date", "Saved as"], rows, height=16)
        if self.rep.folder:
            d.link("Open the Downloads folder", os.path.join(self.rep.folder, "Downloads"))

    def _screens(self):
        shots = list(self.extra_shots)
        if self.rep and self.rep.case:
            shots += [s for c in self.rep.case.walk() for s in c.screenshots]
        folder = os.path.join(self.rep.folder, "Screenshots") if self.rep and self.rep.folder else ""
        if folder and os.path.isdir(folder):
            shots += [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".png")]
        return sorted(set(shots))

    def _screens_view(self, d):
        d.title("Screenshots", "Use 'Screenshot SALTO' or 'Pick & capture' to add more")
        shots = self._screens()
        d.table(["File", "Path"], [[os.path.basename(p), p] for p in shots], height=16)

    def _search(self, d):
        d.title("Search results", f"STC Search for {self.rep.order_ref}")
        width = max((len(r.cells) for r in self.rep.rows), default=0)
        d.table(["STC ID", "Sub-case ID"] + [f"Col {i + 1}" for i in range(2, width)],
                [[r.stc_id, r.sub_case_id] + r.cells[2:] for r in self.rep.rows], height=16)


def _stage_text(c):
    cur = [s.name for s in c.stages if s.state == "current"]
    if cur:
        return f"stage: {cur[0]}"
    if c.stages and all(s.state == "completed" for s in c.stages):
        return "completed"
    return ""
