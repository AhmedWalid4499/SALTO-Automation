"""Reusable widgets: styled tables, cards, nested tabs, stage stepper."""
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import theme as T


# ---------------------------------------------------------------- tables
def table(parent, headers, rows, height=12, widths=None):
    """Scrollable, sortable table. rows: dicts keyed by header, or sequences.
    Ctrl+C / right-click copies rows (tab separated, pastes into Excel)."""
    frame = ctk.CTkFrame(parent, fg_color=T.CARD, corner_radius=8, border_width=1, border_color=T.BORDER)
    inner = tk.Frame(frame, bg=T.CARD)
    inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    tv = ttk.Treeview(inner, columns=list(range(len(headers))), show="headings", height=height)
    for i, h in enumerate(headers):
        tv.heading(i, text=h, anchor=tk.W, command=lambda c=i: _sort(tv, c, False))
        w = (widths or {}).get(h) or max(90, min(340, 8 * max([len(str(h)) + 2] + [len(str(_cell(r, h, i))) for r in rows[:200]])))
        tv.column(i, width=w, anchor=tk.W, stretch=True)
    for k, r in enumerate(rows):
        tv.insert("", tk.END, values=[_cell(r, h, i) for i, h in enumerate(headers)], tags=("odd",) if k % 2 else ())
    tv.tag_configure("odd", background="#FAFAFB")
    ys = ttk.Scrollbar(inner, orient=tk.VERTICAL, command=tv.yview)
    xs = ttk.Scrollbar(inner, orient=tk.HORIZONTAL, command=tv.xview)
    tv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
    tv.grid(row=0, column=0, sticky="nsew")
    ys.grid(row=0, column=1, sticky="ns")
    xs.grid(row=1, column=0, sticky="ew")
    inner.rowconfigure(0, weight=1)
    inner.columnconfigure(0, weight=1)

    def copy(_e=None):
        sel = tv.selection() or tv.get_children()
        text = "\t".join(headers) + "\n" + "\n".join("\t".join(str(v) for v in tv.item(i, "values")) for i in sel)
        tv.clipboard_clear()
        tv.clipboard_append(text)

    tv.bind("<Control-c>", copy)
    menu = tk.Menu(tv, tearoff=0)
    menu.add_command(label="Copy selected rows (or all)", command=copy)
    tv.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
    frame.tree = tv
    return frame


def kv_table(parent, pairs, height=12):
    return table(parent, ["Field", "Value"], [list(p) for p in pairs], height=height,
                 widths={"Field": 280, "Value": 560})


def _cell(r, h, i):
    if isinstance(r, dict):
        return r.get(h, "")
    return r[i] if i < len(r) else ""


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def _sort(tv, col, reverse):
    items = [(tv.set(k, col), k) for k in tv.get_children("")]
    items.sort(key=lambda t: (_num(t[0]) is None, _num(t[0]) if _num(t[0]) is not None else t[0].lower()), reverse=reverse)
    for idx, (_, k) in enumerate(items):
        tv.move(k, "", idx)
        tv.item(k, tags=("odd",) if idx % 2 else ())
    tv.heading(col, command=lambda: _sort(tv, col, not reverse))


# ---------------------------------------------------------------- layout pieces
def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=T.CARD, corner_radius=12, border_width=1, border_color=T.BORDER, **kw)


def stat_card(parent, label, value="—", accent=None):
    c = card(parent)
    ctk.CTkLabel(c, text=label.upper(), font=T.font(10, "bold"), text_color=T.MUTED).pack(anchor="w", padx=14, pady=(10, 0))
    v = ctk.CTkLabel(c, text=value, font=T.font(18, "bold"), text_color=accent or T.INK)
    v.pack(anchor="w", padx=14, pady=(0, 10))
    c.value = v
    return c


def tabs(parent, names, height=380):
    """Horizontal tabs (CTkTabview). Returns (tabview, {name: frame})."""
    tv = ctk.CTkTabview(parent, height=height, fg_color=T.CARD, corner_radius=10, border_width=1, border_color=T.BORDER,
                        segmented_button_selected_color=T.ORANGE, segmented_button_selected_hover_color=T.ORANGE_HOVER,
                        segmented_button_unselected_color="#F3F4F6", segmented_button_unselected_hover_color="#E5E7EB",
                        segmented_button_fg_color="#F3F4F6", text_color=T.INK, anchor="w")
    frames = {}
    for n in names:
        frames[n] = tv.add(n)
    return tv, frames


def empty(parent, title, hint=""):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(f, text=title, font=T.font(15, "bold"), text_color=T.INK).pack(pady=(40, 4))
    if hint:
        ctk.CTkLabel(f, text=hint, font=T.font(12), text_color=T.MUTED).pack()
    return f


def stepper(parent, stages):
    """Stage chevrons: completed green, current blue, pending grey."""
    f = ctk.CTkFrame(parent, fg_color="transparent")
    colors = {"completed": (T.GREEN, "white"), "current": (T.BLUE, "white"), "pending": (T.GREY, T.MUTED)}
    for i, s in enumerate(stages):
        bg, fg = colors.get(s.state, colors["pending"])
        mark = "✓  " if s.state == "completed" else ("●  " if s.state == "current" else "")
        ctk.CTkLabel(f, text=f"{mark}{s.name}", fg_color=bg, text_color=fg, corner_radius=14, height=28,
                     font=T.font(12, "bold" if s.state == "current" else "normal")).pack(side="left", padx=(0 if i == 0 else 6, 0), ipadx=12)
    return f
