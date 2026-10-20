import os
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from salto.actions import order_lookup
from salto.export import export_report
from ui import theme as T
from ui import widgets as W

from .base import Feature


class OrderLookup(Feature):
    title = "Order Lookup"

    def build(self, parent):
        self.rep = None
        self.sections = {}       # section name -> builder(frame)
        self.section_btns = {}
        self.current = None
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=28, pady=22)

        # ---- header
        ctk.CTkLabel(page, text="Order Lookup", font=T.font(24, "bold"), text_color=T.INK).pack(anchor="w")
        ctk.CTkLabel(page, text="Search a commercial order and see everything SALTO knows about it.",
                     font=T.font(13), text_color=T.MUTED).pack(anchor="w", pady=(0, 14))

        # ---- search card
        sc = W.card(page)
        sc.pack(fill="x")
        row = ctk.CTkFrame(sc, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(16, 8))
        self.entry = ctk.CTkEntry(row, placeholder_text="Commercial order reference, e.g. 10-1764901", height=44,
                                  font=T.font(15), corner_radius=10, border_color=T.BORDER, fg_color="#FAFAFB")
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _e: self.go())
        self.btn = ctk.CTkButton(row, text="Get data", width=140, height=44, corner_radius=10, font=T.font(15, "bold"),
                                 fg_color=T.ORANGE, hover_color=T.ORANGE_HOVER, command=self.go)
        self.btn.pack(side="left", padx=(10, 0))
        opts = ctk.CTkFrame(sc, fg_color="transparent")
        opts.pack(fill="x", padx=16, pady=(0, 14))
        self.full = ctk.CTkSwitch(opts, text="Read all tabs", progress_color=T.ORANGE, font=T.font(12), text_color=T.INK)
        self.full.select()
        self.full.pack(side="left")
        self.shot = ctk.CTkSwitch(opts, text="Save screenshot", progress_color=T.ORANGE, font=T.font(12), text_color=T.INK)
        self.shot.pack(side="left", padx=18)
        self.export_btn = ctk.CTkButton(opts, text="Export to Excel", width=140, height=32, corner_radius=8,
                                        fg_color="#F3F4F6", text_color=T.INK, hover_color=T.GREY, state="disabled",
                                        command=self.export)
        self.export_btn.pack(side="right")
        self.progress = ctk.CTkProgressBar(sc, height=4, progress_color=T.ORANGE, fg_color=T.CARD, mode="indeterminate")
        self.status = ctk.CTkLabel(sc, text="", font=T.font(12), text_color=T.MUTED)
        self.app.on_log.append(self._on_log)

        # ---- stats + stepper
        self.stats_row = ctk.CTkFrame(page, fg_color="transparent")
        self.stats_row.pack(fill="x", pady=(14, 0))
        self.stats = {}
        for i, name in enumerate(["STC", "Status", "Current stage", "EQPs", "Devices", "Participants"]):
            c = W.stat_card(self.stats_row, name, accent=T.BLUE if name == "Current stage" else None)
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            self.stats_row.grid_columnconfigure(i, weight=1, uniform="stats")
            self.stats[name] = c
        self.stepper_holder = ctk.CTkFrame(page, fg_color="transparent", height=36)
        self.stepper_holder.pack(fill="x", pady=(12, 0))

        # ---- results
        res = W.card(page)
        res.pack(fill="both", expand=True, pady=(12, 0))
        self.nav = ctk.CTkScrollableFrame(res, width=210, fg_color="#FAFAFB", corner_radius=10)
        self.nav.pack(side="left", fill="y", padx=(8, 0), pady=8)
        self.content = ctk.CTkFrame(res, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        W.empty(self.content, "Search an order to get started",
                "Type a commercial order reference above and press Enter.").pack(fill="both", expand=True)

    # ------------------------------------------------------------ progress
    def _on_log(self, msg):
        if self.btn.cget("state") == "disabled":
            self.status.configure(text=msg)

    def _busy(self, on):
        if on:
            self.progress.pack(fill="x", padx=16, pady=(0, 2))
            self.status.pack(anchor="w", padx=16, pady=(0, 10))
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.status.pack_forget()

    # ------------------------------------------------------------ actions
    def go(self):
        ref = self.entry.get().strip()
        if not ref or self.btn.cget("state") == "disabled":
            return
        path = ""
        if self.shot.get():
            folder = os.path.join(self.app.cfg["export_dir"], "screenshots")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{ref}_{datetime.now():%Y%m%d_%H%M%S}.png")
        full = bool(self.full.get())
        self.app.log(f"--- Lookup {ref} ---")
        self.btn.configure(text="Working...")
        self._busy(True)
        self.status.configure(text=f"Looking up {ref}...")
        self.run(lambda b: order_lookup(b, ref, path, full=full), self.show, self.failed, busy_widgets=(self.btn,))

    def failed(self, exc):
        self._busy(False)
        self.btn.configure(text="Get data")
        messagebox.showerror("SALTO Buddy", f"The lookup failed:\n\n{str(exc).splitlines()[0]}\n\n"
                                            "Open Activity log (left menu) for details.")

    def export(self):
        if not self.rep:
            return
        os.makedirs(self.app.cfg["export_dir"], exist_ok=True)
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialdir=self.app.cfg["export_dir"],
            initialfile=f"{self.rep.order_ref}_{self.rep.stc_id}_{datetime.now():%Y%m%d}.xlsx")
        if path:
            export_report(self.rep, path)
            self.app.log(f"Exported: {path}")
            if messagebox.askyesno("SALTO Buddy", "Excel file saved. Open it now?"):
                os.startfile(path)

    # ------------------------------------------------------------ results
    def show(self, rep):
        self._busy(False)
        self.btn.configure(text="Get data")
        self.rep = rep
        case = rep.case
        self.export_btn.configure(state="normal", fg_color=T.ORANGE_SOFT, text_color=T.ORANGE)
        vals = {"STC": rep.stc_id or "Not found", "Status": rep.status or "—", "Current stage": rep.current_stage or "—",
                "EQPs": str(len(rep.eqps)),
                "Devices": str(len(case.scope_devices)) if case else "—",
                "Participants": str(len(case.participants)) if case else "—"}
        for k, v in vals.items():
            self.stats[k].value.configure(text=v)
        for w in self.stepper_holder.winfo_children():
            w.destroy()
        if rep.stages:
            W.stepper(self.stepper_holder, rep.stages).pack(anchor="w")

        self.sections = {"Summary": lambda f: self._summary(f, rep)}
        if case:
            self.sections[f"Scope of work devices ({len(case.scope_devices)})"] = lambda f: self._scope(f, case)
            self.sections[f"Participants ({len(case.participants)})"] = lambda f: self._participants(f, case)
            for name, td in case.tabs.items():
                if name != "TS":
                    self.sections[name] = (lambda t: lambda f: self._case_tab(f, t))(td)
        self.sections[f"Search results ({len(rep.rows)})"] = lambda f: W.table(
            f, ["STC ID", "Sub-case ID", "Row"],
            [[r.stc_id, r.sub_case_id, " | ".join(c for c in r.cells if c)] for r in rep.rows], height=16
        ).pack(fill="both", expand=True)

        for w in self.nav.winfo_children():
            w.destroy()
        self.section_btns = {}
        ctk.CTkLabel(self.nav, text="RESULTS", font=T.font(10, "bold"), text_color=T.MUTED).pack(anchor="w", padx=8, pady=(4, 4))
        for name in self.sections:
            if name == "Overview":
                ctk.CTkLabel(self.nav, text="SALTO CASE TABS", font=T.font(10, "bold"),
                             text_color=T.MUTED).pack(anchor="w", padx=8, pady=(12, 4))
            b = ctk.CTkButton(self.nav, text=name, anchor="w", height=34, corner_radius=8, font=T.font(13),
                              fg_color="transparent", text_color=T.INK, hover_color="#F3F4F6",
                              command=lambda n=name: self.open_section(n))
            b.pack(fill="x", pady=1)
            self.section_btns[name] = b
        self.open_section("Summary")
        if case and case.errors:
            self.app.log("Some tabs could not be read: " + "; ".join(case.errors))
        if rep.screenshot:
            self.app.log(f"Screenshot: {rep.screenshot}")

    def open_section(self, name):
        for n, b in self.section_btns.items():
            b.configure(fg_color=T.ORANGE_SOFT if n == name else "transparent",
                        text_color=T.ORANGE if n == name else T.INK)
        for w in self.content.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.content, text=name.split(" (")[0], font=T.font(18, "bold"), text_color=T.INK).pack(anchor="w", pady=(0, 8))
        holder = ctk.CTkFrame(self.content, fg_color="transparent")
        holder.pack(fill="both", expand=True)
        self.sections[name](holder)

    # ------------------------------------------------------------ section builders
    def _summary(self, f, rep):
        case = rep.case
        pairs = [("Order reference", rep.order_ref), ("STC ID", rep.stc_id), ("Status", rep.status),
                 ("Current stage", rep.current_stage),
                 ("EQPs", f"{len(rep.eqps)}  ({', '.join(rep.eqps)})" if rep.eqps else "0")]
        if case:
            pairs.append(("Scope of work devices", str(len(case.scope_devices))))
            pairs.append(("Participants", ", ".join(f"{p.name} ({p.role})" for p in case.participants)))
            pairs += case.header
        W.kv_table(f, pairs, height=14).pack(fill="both", expand=True)

    def _scope(self, f, case):
        if not case.scope:
            W.empty(f, "No scope of work found", "This case has no product nodes in its TS tab.").pack(fill="both", expand=True)
            return
        names = _unique([f"{n.node}" for n in case.scope])
        tv, tabs = W.tabs(f, names)
        tv.pack(fill="both", expand=True)
        for n, name in zip(case.scope, names):
            t = tabs[name]
            ctk.CTkLabel(t, text=f"{n.product}  ›  {n.node}", font=T.font(13, "bold"), text_color=T.INK).pack(anchor="w")
            if n.counts:
                chips = ctk.CTkFrame(t, fg_color="transparent")
                chips.pack(anchor="w", pady=(6, 8))
                for k, v in n.counts:
                    ctk.CTkLabel(chips, text=f"{k.replace('Number of Devices to be ', '').capitalize()}: {v}",
                                 fg_color="#F3F4F6", corner_radius=12, height=26, font=T.font(12),
                                 text_color=T.INK).pack(side="left", padx=(0, 6), ipadx=10)
            W.table(t, n.devices.headers, n.devices.rows, height=12).pack(fill="both", expand=True)

    def _participants(self, f, case):
        if not case.participants:
            W.empty(f, "No participants listed").pack(fill="both", expand=True)
            return
        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="x")
        for i, p in enumerate(case.participants):
            c = W.card(grid)
            c.grid(row=i // 3, column=i % 3, sticky="ew", padx=(0, 10), pady=(0, 10))
            grid.grid_columnconfigure(i % 3, weight=1, uniform="p")
            initials = "".join(x[0] for x in p.name.split()[:2]).upper()
            top = ctk.CTkFrame(c, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=14)
            ctk.CTkLabel(top, text=initials, width=40, height=40, corner_radius=20, fg_color=T.ORANGE_SOFT,
                         text_color=T.ORANGE, font=T.font(14, "bold")).pack(side="left")
            txt = ctk.CTkFrame(top, fg_color="transparent")
            txt.pack(side="left", padx=10, fill="x", expand=True)
            ctk.CTkLabel(txt, text=p.name, font=T.font(14, "bold"), text_color=T.INK, anchor="w",
                         justify="left", wraplength=210).pack(anchor="w", fill="x")
            ctk.CTkLabel(txt, text=p.role, font=T.font(12), text_color=T.MUTED, anchor="w",
                         justify="left", wraplength=210).pack(anchor="w", fill="x")

    def _case_tab(self, f, td):
        """A SALTO case tab: one inner tab per section and per table."""
        items = [(sec.title() if sec.isupper() else sec, "kv", fields) for sec, fields in td.sections]
        items += [(f"{g.name if g.name and g.name != 'General' else td.name} ({len(g.rows)})", "grid", g) for g in td.grids]
        if not items:
            W.empty(f, "Nothing in this tab", "SALTO shows no data here for this case.").pack(fill="both", expand=True)
            return
        names = _unique([i[0] for i in items])
        tv, tabs = W.tabs(f, names)
        tv.pack(fill="both", expand=True)
        for (_, kind, data), name in zip(items, names):
            if kind == "kv":
                W.kv_table(tabs[name], data, height=12).pack(fill="both", expand=True)
            else:
                W.table(tabs[name], data.headers, data.rows, height=12).pack(fill="both", expand=True)


def _unique(names):
    seen, out = {}, []
    for n in names:
        n = n[:40]
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} {seen[n]}")
    return out
