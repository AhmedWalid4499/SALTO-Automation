"""Org Chart: find anyone at Orange Business by name or email, with their manager chain and emails."""
import tkinter as tk
from tkinter import ttk

from salto import errors, orgchart
from ui import theme as T
from ui.widgets import RoundButton, RoundEntry, Table

from .base import Feature

COLS = ["Name", "Email", "Job title", "Department", "Country", "Phone", "Manager", "Manager email"]


def _row(p):
    chain = p.get("chain") or []
    return {"Name": p["display_name"], "Email": p["email"], "Job title": p["busi_title"],
            "Department": p["dept_desc"], "Country": p["country_descr"], "Phone": p["phone"] or p["mobile"],
            "Manager": p["supr_display_name"], "Manager email": chain[0]["email"] if chain else ""}


class OrgChartFinder(Feature):
    title = "Org Chart"
    icon = "\uEBDA"
    subtitle = "Emails, jobs and managers from the Orange Business Org Chart"

    def build(self, parent):
        self.people = []
        tk.Label(parent, text="Partial names work. Select a person to see who they report to.", bg=T.CARD,
                 fg=T.MUTED, font=T.F_SMALL, anchor="w").pack(fill="x", pady=(0, 10))
        bar = ttk.Frame(parent, style="Card.TFrame")
        bar.pack(fill="x")
        self.vars = {}
        for label, width in (("Last name", 12), ("First name", 10), ("Email", 18)):
            ttk.Label(bar, text=label, font=T.F_BOLD).pack(side="left", padx=(0 if not self.vars else 12, 6))
            v = tk.StringVar()
            e = RoundEntry(bar, textvariable=v, width=width * 12)
            e.pack(side="left")
            e.bind("<Return>", lambda _e: self.search())
            self.vars[label] = v
        self.btn = RoundButton(bar, "Search", self.search)
        self.btn.pack(side="left", padx=12)
        self.info = tk.Label(parent, text="", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL, anchor="w")
        self.info.pack(fill="x", pady=(10, 4))
        self.top = tk.Frame(parent, bg=T.CARD)
        self.top.pack(fill="x")
        tk.Label(parent, text="Management chain of the selected person", bg=T.CARD, fg=T.ORANGE,
                 font=T.F_SECTION, anchor="w").pack(fill="x", pady=(12, 4))
        self.low = tk.Frame(parent, bg=T.CARD)
        self.low.pack(fill="both", expand=True)

    def search(self):
        last, first, email = (self.vars[k].get().strip() for k in ("Last name", "First name", "Email"))
        if not (last or first or email):
            self.info.configure(text="Type a last name, a first name or an email.", fg=T.RED)
            return
        self.info.configure(text="Searching the Org Chart...", fg=T.MUTED)
        self.app.busy(True, "Searching the Org Chart...")

        def done(people):
            self.app.busy(False)
            self.show(people)

        def failed(exc):
            self.app.busy(False)
            self.info.configure(text=errors.friendly(exc), fg=T.RED)

        self.run(lambda b: orgchart.find(b, last, first, email, log=self.app.log), done, failed,
                 busy_widgets=(self.btn,))

    def show(self, people):
        self.people = people
        for w in list(self.top.winfo_children()) + list(self.low.winfo_children()):
            w.destroy()
        if not people:
            self.info.configure(text="Nobody found. Customer contacts are not in the Org Chart.", fg=T.MUTED)
            return
        self.info.configure(text=f"{len(people)} person(s) found" + (" (first 15 shown)" if len(people) >= 15 else "")
                                 + ". Select one to see their management chain. Ctrl+C copies rows.", fg=T.MUTED)
        t = Table(self.top, COLS, [_row(p) for p in people], height=min(len(people), 8))
        t.pack(fill="x")
        # row id -> person, taken before any sorting (a sort moves rows, it keeps their ids)
        self._by_row = dict(zip(t.tv.get_children(), people))
        t.tv.bind("<<TreeviewSelect>>", lambda e: self._chain(t))
        t.tv.selection_set(t.tv.get_children()[0])

    def _chain(self, t):
        sel = t.tv.selection()
        if not sel:
            return
        p = self._by_row.get(sel[0])
        if p is None:
            return
        for w in self.low.winfo_children():
            w.destroy()
        rows = [{"Level": "Person", "Name": p["display_name"], "Email": p["email"], "Job title": p["busi_title"],
                 "Department": p["dept_desc"], "Country": p["country_descr"]}]
        for i, m in enumerate(p.get("chain") or [], 1):
            level = "Manager" if i == 1 else f"{i}{'nd' if i == 2 else 'rd' if i == 3 else 'th'}-level manager"
            rows.append({"Level": level, "Name": m["display_name"],
                         "Email": m["email"], "Job title": m["busi_title"], "Department": m["dept_desc"],
                         "Country": m["country_descr"]})
        Table(self.low, ["Level", "Name", "Email", "Job title", "Department", "Country"], rows,
              height=len(rows)).pack(fill="both", expand=True)
