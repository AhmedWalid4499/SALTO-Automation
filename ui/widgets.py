"""Flat widgets: tables, a wrapping detail view, status cards, stage stepper, status pill."""
import math
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import theme as T


# ---------------------------------------------------------------- data table
class Table(ttk.Frame):
    """Sortable table with zebra rows. Ctrl+C / right-click copies (pastes into Excel).
    Double-click a row with a file path in 'Saved as' (or 'Path') to open the file."""

    def __init__(self, parent, headers, rows, height=10, widths=None):
        super().__init__(parent, style="Card.TFrame")
        self.headers = list(headers)
        self.tv = tv = ttk.Treeview(self, columns=list(range(len(self.headers))), show="headings",
                                    height=max(1, min(height, len(rows) or 1)))
        body, head = tkfont.Font(font=T.F_BODY), tkfont.Font(font=T.F_SMALL_BOLD)
        for i, h in enumerate(self.headers):
            tv.heading(i, text=h, anchor=tk.W, command=lambda c=i: self._sort(c, False))
            longest = max([str(_cell(r, h, i)) for r in rows[:200]] + [""], key=len)
            w = (widths or {}).get(h) or max(60, min(420, max(head.measure(h) + 26, body.measure(longest) + 18)))
            tv.column(i, width=w, minwidth=50, anchor=tk.W, stretch=True)
        for k, r in enumerate(rows):
            tv.insert("", tk.END, values=[_cell(r, h, i) for i, h in enumerate(self.headers)],
                      tags=("odd",) if k % 2 else ())
        tv.tag_configure("odd", background=T.ZEBRA)
        ys = ttk.Scrollbar(self, orient=tk.VERTICAL, command=tv.yview)
        xs = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=tv.xview)
        tv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        tv.grid(row=0, column=0, sticky="nsew")
        if len(rows) > height:
            ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        tv.bind("<Control-c>", self.copy)
        tv.bind("<Double-1>", self._open)
        menu = tk.Menu(tv, tearoff=0)
        menu.add_command(label="Copy selected rows (or all)", command=self.copy)
        tv.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def copy(self, _e=None):
        sel = self.tv.selection() or self.tv.get_children()
        text = "\t".join(self.headers) + "\n" + "\n".join(
            "\t".join(str(v) for v in self.tv.item(i, "values")) for i in sel)
        self.clipboard_clear()
        self.clipboard_append(text)

    def _open(self, _e):
        for col in ("Saved as", "Path"):
            if col in self.headers:
                sel = self.tv.selection()
                if sel:
                    p = self.tv.item(sel[0], "values")[self.headers.index(col)]
                    if p and os.path.exists(p):
                        os.startfile(p)

    def _sort(self, col, reverse):
        items = [(self.tv.set(k, col), k) for k in self.tv.get_children("")]
        items.sort(key=lambda t: (_num(t[0]) is None, _num(t[0]) if _num(t[0]) is not None else t[0].lower()),
                   reverse=reverse)
        for idx, (_, k) in enumerate(items):
            self.tv.move(k, "", idx)
            self.tv.item(k, tags=("odd",) if idx % 2 else ())
        self.tv.heading(col, command=lambda: self._sort(col, not reverse))


def _cell(r, h, i):
    if isinstance(r, dict):
        return r.get(h, "")
    return r[i] if i < len(r) else ""


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------- detail view
class DetailView(ttk.Frame):
    """Scrollable, wrapping view: orange section headings, bold labels, values; tables inline.
    Label column width follows the window, so long values wrap instead of running off a small screen."""

    def __init__(self, parent):
        super().__init__(parent, style="Card.TFrame")
        self.text = tk.Text(self, wrap="word", borderwidth=0, highlightthickness=0, bg=T.CARD, fg=T.INK,
                            font=T.F_BODY, padx=14, pady=10, cursor="arrow", spacing1=2, spacing3=2)
        ys = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=ys.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        t = self.text
        t.tag_configure("title", font=T.F_TITLE, spacing3=6)
        t.tag_configure("subtitle", font=T.F_SMALL, foreground=T.MUTED, spacing3=8)
        t.tag_configure("section", font=T.F_SECTION, foreground=T.ORANGE, spacing1=12, spacing3=4)
        t.tag_configure("label", font=T.F_BOLD, foreground=T.MUTED)
        t.tag_configure("value", font=T.F_BODY, foreground=T.INK)
        t.tag_configure("empty", font=T.F_BODY, foreground=T.SUBTLE)
        t.tag_configure("note", font=T.F_SMALL, foreground=T.MUTED, spacing1=4)
        t.tag_configure("para", font=T.F_BODY, foreground=T.INK, spacing1=4, spacing3=6)
        t.tag_configure("bullet", font=T.F_BODY, foreground=T.INK, lmargin1=6, lmargin2=22, spacing1=2)
        t.tag_configure("stepnum", font=T.F_BOLD, foreground=T.ORANGE)
        t.tag_configure("step", tabs=(28,), lmargin1=6, lmargin2=28, spacing1=3)
        t.tag_configure("link", font=T.F_BODY, foreground=T.ORANGE, underline=True)
        t.tag_bind("link", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda e: t.configure(cursor="arrow"))
        self._tables = []
        self._links = 0
        t.bind("<Configure>", self._relayout)
        t.bind("<MouseWheel>", lambda e: t.yview_scroll(int(-e.delta / 120), "units"))
        t.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for w in self._tables:
            w.destroy()
        self._tables = []
        self.text.configure(state="disabled")

    def _put(self, s, *tags):
        self.text.configure(state="normal")
        self.text.insert("end", s, tags)
        self.text.configure(state="disabled")

    def title(self, text, subtitle=""):
        self._put(text + "\n", "title")
        if subtitle:
            self._put(subtitle + "\n", "subtitle")

    def section(self, name):
        self._put(name + "\n", "section")

    def fields(self, pairs):
        for label, value in pairs:
            self._put(f"{label}\t", "label", "kv")
            self._put(f"{value}\n" if value else "—\n", "value" if value else "empty", "kv")

    def note(self, text):
        self._put(text + "\n", "note")

    def note_body(self, text):
        """A normal paragraph."""
        self._put(text + "\n", "para")

    def bullet(self, text):
        self._put("•  " + text + "\n", "bullet")

    def step(self, n, text):
        """Numbered step: orange number, text wrapping under itself."""
        self._put(f"{n}\t", "stepnum", "step")
        self._put(text + "\n", "para", "step")

    def link(self, text, path):
        tag = f"l{self._links}"
        self._links += 1
        self.text.tag_bind(tag, "<Button-1>", lambda e: os.path.exists(path) and os.startfile(path))
        self._put(text + "\n", "link", tag)

    def table(self, headers, rows, height=12):
        if not rows:
            self._put("No rows.\n", "empty")
            return
        tbl = Table(self.text, headers, rows, height=height)
        self._tables.append(tbl)
        self.text.configure(state="normal")
        self.text.window_create("end", window=tbl, stretch=1)
        self.text.insert("end", "\n")
        self.text.configure(state="disabled")
        self._size_table(tbl)

    def _size_table(self, tbl):
        w = max(300, self.text.winfo_width() - 40)
        tbl.configure(width=w)
        tbl.grid_propagate(False)
        rows = min(int(tbl.tv.cget("height")), 12)
        tbl.configure(height=int((rows + 2.3) * T._px(self, 28)))

    def _relayout(self, e):
        # label column: 32% of the width, between 140 and 300 px (small screens give values the room)
        col = max(140, min(300, int(e.width * 0.32)))
        self.text.tag_configure("kv", tabs=(col,), lmargin1=0, lmargin2=col)
        for tbl in self._tables:
            self._size_table(tbl)


# ---------------------------------------------------------------- small pieces
class Stepper(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=T.CARD)

    def set(self, stages):
        for w in self.winfo_children():
            w.destroy()
        for i, s in enumerate(stages):
            rag = {"completed": "green", "current": "blue"}.get(s.state, "grey")
            fg, bg = T.RAG[rag]
            mark = "✓ " if s.state == "completed" else ("● " if s.state == "current" else "")
            tk.Label(self, text=f"{mark}{s.name}", bg=bg, fg=fg, padx=10, pady=3,
                     font=T.F_SMALL_BOLD if s.state == "current" else T.F_SMALL).pack(side="left", padx=(0 if i == 0 else 4, 0))
            if i < len(stages) - 1:
                tk.Label(self, text="›", bg=T.CARD, fg=T.SUBTLE, font=T.F_BODY).pack(side="left", padx=(4, 0))


class Segmented(tk.Frame):
    """Buttons side by side; the selected one is dark (a 2-6 way choice, e.g. tabs of a sub-case)."""

    def __init__(self, parent, options, command, value=None):
        super().__init__(parent, bg=T.CARD)
        self.command, self.btns = command, {}
        for i, opt in enumerate(options):
            b = tk.Label(self, text=opt, font=T.F_SMALL_BOLD, padx=14, pady=6, cursor="hand2",
                         bg=T.FIELD, fg=T.INK, highlightthickness=0)
            b.grid(row=i // 8, column=i % 8, padx=(0, 4), pady=(0, 4), sticky="w")
            b.bind("<Button-1>", lambda e, o=opt: self.select(o))
            b.bind("<Enter>", lambda e, b=b: b.cget("bg") != T.DARK and b.configure(bg=T.BUTTON_HOVER))
            b.bind("<Leave>", lambda e, b=b: b.cget("bg") != T.DARK and b.configure(bg=T.FIELD))
            self.btns[opt] = b
        if options:
            self.select(value or options[0], fire=False)

    def select(self, opt, fire=True):
        for o, b in self.btns.items():
            on = o == opt
            b.configure(bg=T.DARK if on else T.FIELD, fg="white" if on else T.INK)
        self.value = opt
        if fire:
            self.command(opt)


class ThinProgress(tk.Frame):
    """3 px indeterminate progress line: an orange segment sliding across."""

    def __init__(self, parent):
        super().__init__(parent, bg=T.LINE, height=3)
        self.seg = tk.Frame(self, bg=T.ORANGE, height=3)
        self._pos, self._job = 0.0, None

    def start(self, _interval=None):
        self.stop()
        self._tick()

    def _tick(self):
        self._pos = (self._pos + 0.02) % 1.2
        self.seg.place(relx=self._pos - 0.2, rely=0, relwidth=0.2, relheight=1)
        self._job = self.after(30, self._tick)

    def stop(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None


def _round_points(x1, y1, x2, y2, r, steps=8):
    """Polygon points of a rounded rectangle with true quarter-circle corners (r = half the height: a pill)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = []
    for cx, cy, start in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for i in range(steps + 1):
            a = math.radians(start + 90 * i / steps)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def _scale(widget):
    """Windows display scaling (1.0 at 100 %, 1.5 at 150 %): canvas sizes are in pixels and do not follow it."""
    try:
        return max(1.0, widget.winfo_fpixels("1i") / 96)
    except tk.TclError:
        return 1.0


def _bg_of(widget):
    try:
        return widget.cget("bg")
    except tk.TclError:  # ttk widget: its style's background
        return ttk.Style().lookup(widget.cget("style") or widget.winfo_class(), "background") or T.CANVAS


class RoundCard(tk.Canvas):
    """A rounded card. Put content in .inner (a Frame). fit=True: the card is as tall as its content."""

    def __init__(self, parent, fill=T.CARD, radius=18, pad=16, fit=False, shadow=True, **kw):
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, **kw)
        self.fill, self.radius, self.pad, self.fit, self.shadow = fill, radius, pad, fit, shadow
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window(pad, pad, window=self.inner, anchor="nw")
        self.bind("<Configure>", self._redraw)
        if fit:
            self.inner.bind("<Configure>", self._fit, add="+")

    def _fit(self, _e=None):
        h = self.inner.winfo_reqheight() + 2 * self.pad
        if int(self.cget("height")) != h:
            self.configure(height=h)

    def _redraw(self, _e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        self.delete("shape")
        if self.shadow:  # a 1 px soft edge under the card
            self.create_polygon(_round_points(0, 1, w - 1, h - 1, self.radius), fill=T.SHADOW,
                                outline="", tags="shape")
        self.create_polygon(_round_points(0, 0, w - 1, h - 2 if self.shadow else h - 1, self.radius),
                            fill=self.fill, outline="", tags=("shape", "body"))
        self.tag_lower("shape")
        self.itemconfigure(self._win, width=max(1, w - 2 * self.pad))
        if not self.fit:
            self.itemconfigure(self._win, height=max(1, h - 2 * self.pad - (1 if self.shadow else 0)))

    def recolor(self, fill):
        """New card colour (the inner frame and its direct plain children follow)."""
        old, self.fill = self.fill, fill
        self.itemconfigure("body", fill=fill)
        self.inner.configure(bg=fill)
        for w in self.inner.winfo_children():
            with _suppress_tcl():
                if w.cget("bg") == old:
                    w.configure(bg=fill)


class _suppress_tcl:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, *exc):
        return exc_type is not None and issubclass(exc_type, tk.TclError)


class NavItem(tk.Canvas):
    """A sidebar entry: icon + label on a rounded highlight (orange tint when selected)."""

    def __init__(self, parent, icon, text, command, width=170, height=40, badge=False):
        self.k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, width=int(width * self.k),
                         height=int(height * self.k), cursor="hand2")
        self.icon, self.text, self.command, self.badge = icon, text, command, badge
        self.selected = self.hover = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: self.command())

    def _set_hover(self, on):
        self.hover = on
        self._draw()

    def set(self, selected=None, text=None, badge=None):
        if selected is not None:
            self.selected = selected
        if text is not None:
            self.text = text
        if badge is not None:
            self.badge = badge
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        if self.selected or self.hover:
            self.create_polygon(_round_points(0, 0, w - 1, h - 1, h // 2), outline="",
                                fill=T.ORANGE_TINT if self.selected else T.NAV_HOVER)
        fg = T.ORANGE if self.selected else (T.INK if self.hover else "#4B5563")
        self.create_text(int(14 * self.k), h // 2, text=self.icon, font=T.F_ICON, fill=fg, anchor="w")
        self.create_text(int(44 * self.k), h // 2, text=self.text, font=T.F_BOLD if self.selected else T.F_BODY,
                         fill=fg, anchor="w")
        if self.badge:  # small orange dot: something new (an update)
            self.create_oval(w - 22, h // 2 - 4, w - 14, h // 2 + 4, fill=T.ORANGE, outline="")


class Pill(tk.Canvas):
    """Status pill: coloured dot + short text on a rounded grey background."""

    def __init__(self, parent, width=170, height=34):
        k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, width=int(width * k),
                         height=int(height * k))
        self.text, self.color = "Starting...", T.SUBTLE
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, text, color):
        self.text, self.color = text[:60], color
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.create_polygon(_round_points(0, 0, w - 1, h - 1, h // 2), fill=T.NAV_HOVER, outline="")
        self.create_oval(14, h // 2 - 4, 22, h // 2 + 4, fill=self.color, outline="")
        text = self.text
        f = tkfont.Font(font=T.F_SMALL)
        while text and f.measure(text) > w - 44:
            text = text[:-2]
        if text != self.text:
            text = text.rstrip() + "…"
        self.create_text(32, h // 2, text=text, font=T.F_SMALL, fill=T.INK, anchor="w")


# key-figure card colours: variant -> (card, caption, value)
_KPI = {"plain": (T.STATUS_CARD, T.MUTED, T.INK), "dark": (T.DARK, "#AEBDBD", "white"),
        "accent": (T.ORANGE, "#FFE3CC", "white")}


class StatusCard(RoundCard):
    """A key figure: small caption, big value. variant: plain (soft grey), dark (slate) or accent (orange)."""

    def __init__(self, parent, caption, value="—", variant="plain"):
        card, cap, val = _KPI[variant]
        super().__init__(parent, fill=card, radius=20, pad=14, fit=True, shadow=variant == "plain")
        self.variant = variant
        self.cap = tk.Label(self.inner, text=caption, bg=card, fg=cap, font=T.F_SMALL, anchor="w")
        self.cap.pack(fill="x")
        self.val = tk.Label(self.inner, text=value, bg=card, fg=val, font=T.F_KPI, anchor="w")
        self.val.pack(fill="x", pady=(2, 0))
        self.bind("<Configure>", lambda e: self._fitfont(), add="+")

    def set(self, value, rag=None):
        card, cap, val = _KPI[self.variant]
        if rag and self.variant == "plain":  # status colours only on plain cards
            val, card = T.RAG.get(rag, (val, card))
        self.recolor(card)
        self.cap.configure(bg=card, fg=cap)
        self.value = value or "—"
        self.val.configure(text=self.value, fg=val, bg=card)
        self._fitfont()
        self.after(50, self._fitfont)  # again once the card has its final width

    def _fitfont(self):
        """Largest font that fits the card; a long value ("Resolved-Completed") goes on two lines rather than
        being cut."""
        room = self.winfo_width() - 2 * self.pad - 8
        if room <= 0:
            return
        text = getattr(self, "value", self.val.cget("text"))
        cut = max(text.find("-"), text.find(" "))
        options = [(text, s) for s in (20, 17, 15, 13, 12)]
        if cut > 0:  # two lines, split after the hyphen / at the space
            two = text[:cut + 1].rstrip() + "\n" + text[cut + 1:].lstrip()
            options += [(two, s) for s in (13, 12, 11, 10)]
        options += [(text, s) for s in (11, 10, 9)]
        for shown, size in options:
            f = tkfont.Font(family=T.FONT, size=size, weight="bold")
            if max(f.measure(line) for line in shown.split("\n")) <= room:
                break
        self.val.configure(text=shown, font=(T.FONT, size, "bold"), justify="left")


class Tooltip:
    """A small dark label under a widget while the mouse is over it."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip or not self.text:
            return
        w = self.widget
        self.tip = tk.Toplevel(w)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        tk.Label(self.tip, text=self.text, bg=T.DARK, fg="white", font=T.F_SMALL, padx=8, pady=4).pack()
        self.tip.update_idletasks()
        x = w.winfo_rootx() + w.winfo_width() // 2 - self.tip.winfo_reqwidth() // 2
        self.tip.geometry(f"+{x}+{w.winfo_rooty() + w.winfo_height() + 6}")

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class IconButton(tk.Label):
    """A square icon button (Segoe MDL2 glyph) with a tooltip; configure(state="disabled") greys it out."""

    def __init__(self, parent, icon, tip, command, size=None):
        k = _scale(parent)
        super().__init__(parent, text=icon, font=(T.ICONS, 13), bg=T.FIELD, fg=T.INK, cursor="hand2",
                         width=3, pady=int(6 * k / 1.5) + 4)
        self._command, self._state = command, "normal"
        self.bind("<Button-1>", lambda e: self._state == "normal" and self._command())
        self.bind("<Enter>", lambda e: self._state == "normal" and tk.Label.configure(self, bg=T.BUTTON_HOVER), add="+")
        self.bind("<Leave>", lambda e: tk.Label.configure(self, bg=T.FIELD), add="+")
        Tooltip(self, tip)

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            kw["fg"] = T.INK if self._state == "normal" else "#B8BDC4"
            kw["cursor"] = "hand2" if self._state == "normal" else ""
        return tk.Label.configure(self, cnf, **kw)

    config = configure


def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


class GradientTile(tk.Canvas):
    """A dashboard key figure on a rounded gradient tile: caption, big value, small note."""

    def __init__(self, parent, caption, colors, value="—", note="", height=88):
        k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, height=int(height * k))
        self.k, self.caption, self.colors, self.value, self.note = k, caption, colors, value, note
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value, note=""):
        self.value, self.note = value, note
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        r = int(16 * self.k)
        for x in range(w):  # one vertical line per pixel, clipped to the rounded rectangle
            dx = r - x if x < r else (x - (w - 1 - r) if x > w - 1 - r else 0)
            inset = r - (r * r - dx * dx) ** 0.5 if dx > 0 else 0
            self.create_line(x, inset, x, h - inset, fill=_mix(self.colors[0], self.colors[1], x / max(1, w - 1)))
        pad = int(16 * self.k)
        self.create_text(pad, pad, text=self.caption, fill="white", font=T.F_SMALL, anchor="nw")
        self.create_text(pad, h - pad - (int(16 * self.k) if self.note else 0), text=self.value, fill="white",
                         font=(T.FONT, 20, "bold"), anchor="sw")
        if self.note:
            self.create_text(pad, h - pad + int(2 * self.k), text=self.note, fill="#F1F5FF", font=T.F_SMALL,
                             anchor="sw")


class BarChart(tk.Canvas):
    """Vertical bars with rounded tops, value labels and soft grid lines. data: [(label, value, colour)]."""

    def __init__(self, parent, height=220):
        k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, height=int(height * k))
        self.k, self.data = k, []
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, data):
        self.data = list(data)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20:
            return
        k = self.k
        if not self.data:
            self.create_text(w // 2, h // 2, text="No data yet: open an order", fill=T.SUBTLE, font=T.F_SMALL)
            return
        top, bottom, left = int(18 * k), int(34 * k), int(30 * k)
        peak = max(v for _, v, _ in self.data) or 1
        step = max(1, -(-peak // 4))
        scale = max(peak, step * 4)
        for i in range(5):  # grid lines with their value
            y = h - bottom - (h - bottom - top) * (i * step) / scale
            self.create_line(left, y, w, y, fill=T.LINE)
            self.create_text(left - 6, y, text=str(i * step), fill=T.SUBTLE, font=(T.FONT, 8), anchor="e")
        slot = (w - left) / len(self.data)
        bar = min(slot * 0.55, 56 * k)
        f = tkfont.Font(font=(T.FONT, 8))
        base = h - bottom
        for i, (label, value, color) in enumerate(self.data):
            x = left + slot * i + (slot - bar) / 2
            y = base - (base - top) * value / scale
            if value:
                rr = min(bar / 2, 8 * k, (base - y))
                self.create_polygon(_round_points(x, y, x + bar, base + rr, rr), fill=color, outline="")
                self.create_rectangle(x - 1, base, x + bar + 1, base + rr + 2, fill=_bg_of(self), outline="")
            self.create_text(x + bar / 2, y - 4, text=str(value), fill=T.INK, font=T.F_SMALL_BOLD, anchor="s")
            text = label
            while text and f.measure(text) > slot - 6:
                text = text[:-2]
            if text != label:
                text = text.rstrip() + "…"
            self.create_text(x + bar / 2, base + 8, text=text, fill=T.MUTED, font=(T.FONT, 8), anchor="n")


class RoundButton(tk.Canvas):
    """A pill-shaped button. kind: accent (orange), dark, soft. configure(state=..., text=...) like a ttk button."""

    _COLORS = {"accent": (T.ORANGE, T.ORANGE_DARK, "white"), "dark": (T.DARK, T.DARK_SOFT, "white"),
               "soft": (T.FIELD, T.BUTTON_HOVER, T.INK)}

    def __init__(self, parent, text, command, kind="accent", padx=20, height=36, font=None):
        self.k = _scale(parent)
        self.text, self.command, self.kind, self.padx = text, command, kind, padx
        self.font = font or T.F_BOLD
        self.state, self.hover = "normal", False
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, height=int(height * self.k),
                         width=self._width(), cursor="hand2")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Button-1>", lambda e: self.state == "normal" and self.command())

    def _width(self):
        return int(tkfont.Font(font=self.font).measure(self.text) + 2 * self.padx * self.k)

    def _hover(self, on):
        self.hover = on
        self._draw()

    def configure(self, cnf=None, **kw):
        changed = False
        if "state" in kw:
            self.state = kw.pop("state")
            changed = True
        if "text" in kw:
            self.text = kw.pop("text")
            kw["width"] = self._width()
            changed = True
        kw.pop("style", None)
        result = tk.Canvas.configure(self, cnf, **kw) if (cnf or kw) else None
        if changed:
            self._draw()
        return result

    config = configure

    def cget(self, key):
        if key == "state":
            return self.state
        if key == "text":
            return self.text
        return tk.Canvas.cget(self, key)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        base, hover, fg = self._COLORS[self.kind]
        fill = hover if self.hover and self.state == "normal" else base
        if self.state != "normal":
            fill, fg = ("#F7C49A", "white") if self.kind == "accent" else (T.FIELD, "#A0A4AB")
        self.create_polygon(_round_points(0, 0, w - 1, h - 1, h // 2), fill=fill, outline="")
        self.create_text(w // 2, h // 2, text=self.text, fill=fg, font=self.font)
        tk.Canvas.configure(self, cursor="hand2" if self.state == "normal" else "")


class RoundEntry(tk.Canvas):
    """A text field with rounded ends (grey; orange outline when focused). .entry is the tk.Entry inside;
    get / insert / delete / bind / focus_set go to it, so it replaces a ttk.Entry."""

    def __init__(self, parent, textvariable=None, width=200, height=38, font=None, show=""):
        k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, width=int(width * k),
                         height=int(height * k))
        self.focused = False
        self.entry = tk.Entry(self, textvariable=textvariable, bd=0, relief="flat", bg=T.FIELD, fg=T.INK,
                              font=font or (T.FONT, 11), insertbackground=T.INK, highlightthickness=0, show=show)
        self._win = self.create_window(0, 0, window=self.entry, anchor="w")
        self.entry.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        tk.Canvas.bind(self, "<Configure>", lambda e: self._draw())
        tk.Canvas.bind(self, "<Button-1>", lambda e: self.entry.focus_set())

    def _focus(self, on):
        self.focused = on
        self._draw()

    def _draw(self):
        tk.Canvas.delete(self, "shape")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        r = h // 2
        if self.focused:
            self.create_polygon(_round_points(0, 0, w - 1, h - 1, r), fill=T.ORANGE, outline="",
                                tags="shape")
            self.create_polygon(_round_points(2, 2, w - 3, h - 3, r - 2), fill=T.FIELD, outline="",
                                tags="shape")
        else:
            self.create_polygon(_round_points(0, 0, w - 1, h - 1, r), fill=T.FIELD, outline="",
                                tags="shape")
        self.tag_lower("shape")
        self.coords(self._win, max(12, r * 0.7), h // 2)
        self.itemconfigure(self._win, width=max(10, w - 2 * max(12, r * 0.7)))

    def get(self):
        return self.entry.get()

    def delete(self, *args):
        return self.entry.delete(*args)

    def insert(self, *args):
        return self.entry.insert(*args)

    def bind(self, seq=None, func=None, add=None):
        return self.entry.bind(seq, func, add)

    def focus_set(self):
        self.entry.focus_set()
