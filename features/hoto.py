"""HOTO preparation: the LAN hand-over sheet filled from the order open in Order explorer."""
import os
import tkinter as tk
from tkinter import filedialog, ttk

from salto import files, hoto
from ui import dialogs as messagebox
from ui import theme as T
from ui.widgets import RoundButton, Table

from .base import Feature


class HotoPrep(Feature):
    title = "HOTO preparation"
    icon = "\uE9D5"  # checklist
    subtitle = "The HOTO sheet of a LAN order, filled from SALTO and FLIP"

    def build(self, parent):
        self.rows = []
        bar = ttk.Frame(parent, style="Card.TFrame")
        bar.pack(fill="x")
        self.save_btn = RoundButton(bar, "Save HOTO Excel", self.save)
        self.save_btn.configure(state="disabled")
        self.save_btn.pack(side="right")
        self.copy_btn = RoundButton(bar, "Copy all rows", self.copy, kind="soft")
        self.copy_btn.configure(state="disabled")
        self.copy_btn.pack(side="right", padx=6)
        intro = tk.Label(bar, text="One row per device in creation, from the order open in Order explorer. Admin and "
                                   "customer IP addresses are not in SALTO: fill them in Excel.", bg=T.CARD,
                         fg=T.MUTED, font=T.F_SMALL, anchor="w", justify="left")
        intro.pack(side="left", fill="x", expand=True)
        intro.bind("<Configure>", lambda e: intro.configure(wraplength=max(200, e.width - 10)))
        self.info = tk.Label(parent, text="", bg=T.CARD, fg=T.INK, font=T.F_BODY, anchor="w", justify="left",
                             wraplength=1100)
        self.info.pack(fill="x")
        self.info.bind("<Configure>", lambda e: self.info.configure(wraplength=max(200, e.width - 10)))
        self.body = tk.Frame(parent, bg=T.CARD)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        self.table = None
        parent.bind("<Map>", lambda e: self.refresh())

    def order_updated(self, rep):
        """Order explorer read (more of) an order: refill if it is the one on screen there."""
        self.refresh()

    def refresh(self):
        ex = self.app.explorer
        rep = ex.rep if ex else None
        for w in self.body.winfo_children():
            w.destroy()
        self.rows, self.table = [], None
        state = "disabled"
        if not rep or not rep.case:
            self.info.configure(text="Open an order in Order explorer first: its HOTO sheet appears here.", fg=T.MUTED)
        elif not hoto.is_lan(rep):
            self.info.configure(text=f"{rep.order_ref} ({rep.stc_id}) is not a LAN project: HOTO preparation is for "
                                     "Managed LAN orders.", fg=T.MUTED)
        else:
            self.rows = hoto.build(rep)
            loading = any(c.startswith("EQP-") for c in rep.case.pending_subs)
            todo = sum(1 for r in self.rows if hoto.needs_check(r))
            text = f"{rep.order_ref}  ·  {rep.stc_id}  ·  {len(self.rows)} device(s) in creation  ·  " \
                   f"{len(self.rows) - todo} serial number(s) found"
            if loading:
                text += "  (serial numbers are still being read from FLIP, they fill in by themselves)"
            elif todo:
                text += f"  ·  {todo} to check: missing, or FLIP lists several for the device (highlighted in Excel; " \
                        "see the FLIP serial numbers tab in Order explorer)"
            self.info.configure(text=text if self.rows else f"{rep.order_ref}: no device in creation in the scope "
                                                              "of work.", fg=T.INK if self.rows else T.MUTED)
            if self.rows:
                self.table = Table(self.body, hoto.COLUMNS, self.rows, height=18)
                self.table.pack(fill="both", expand=True)
                state = "normal"
        self.save_btn.configure(state=state)
        self.copy_btn.configure(state=state)

    def copy(self):
        if self.table:
            self.table.tv.selection_remove(self.table.tv.selection())
            self.table.copy()
            self.app.log("HOTO rows copied: paste them into the HOTO document.")

    def save(self):
        rep = self.app.explorer.rep
        folder = rep.folder or self.app.cfg.get("export_dir", "")
        name = files.safe(f"HOTO {rep.order_ref} - {rep.stc_id}", 80) + ".xlsx"
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                            initialdir=folder if os.path.isdir(folder) else None, initialfile=name)
        if not path:
            return
        try:
            hoto.save(self.rows, path, rep=self.app.explorer.rep)
        except OSError as exc:
            messagebox.showerror("SALTO Buddy", f"Could not save the HOTO sheet:\n{exc}\n\n"
                                                "Is it open in Excel? Close it and try again.")
            return
        self.app.log(f"Saved {path}")
        if messagebox.askyesno("SALTO Buddy", f"Saved to {path}\n\nOpen it now?"):
            os.startfile(path)
