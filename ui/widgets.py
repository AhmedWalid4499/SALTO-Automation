"""Widgets: tables, a wrapping detail view, and smooth rounded cards, buttons and fields (drawn by gfx)."""
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import gfx
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
        tv.configure(yscrollcommand=_auto(ys, row=0, column=1, sticky="ns"),
                     xscrollcommand=_auto(xs, row=1, column=0, sticky="ew"))
        tv.grid(row=0, column=0, sticky="nsew")
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


def _auto(bar, **grid):
    """A scroll command that shows the scroll bar only when there is something to scroll."""
    def update(first, last):
        bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            bar.grid_remove()
        else:
            bar.grid(**grid)
    return update


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
                            font=T.F_BODY, padx=6, pady=8, cursor="arrow", spacing1=2, spacing3=2)
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
        tbl.configure(height=int((rows + 2.3) * T._px(self, 32)))

    def _relayout(self, e):
        # label column: 32% of the width, between 140 and 300 px (small screens give values the room)
        col = max(140, min(300, int(e.width * 0.32)))
        self.text.tag_configure("kv", tabs=(col,), lmargin1=0, lmargin2=col)
        for tbl in self._tables:
            self._size_table(tbl)


# ---------------------------------------------------------------- small pieces
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


class Stepper(tk.Canvas):
    """The stages of an order: green tick done, orange ring current, grey ring to come, joined by a line."""

    def __init__(self, parent):
        self.k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, width=1, height=int(26 * self.k))
        self._imgs = []

    def set(self, stages):
        self.delete("all")
        self._imgs = []
        k, y, x = self.k, int(13 * self.k), 0
        d = int(18 * k)
        for i, s in enumerate(stages):
            done, current = s.state == "completed", s.state == "current"
            if done:
                node = gfx.dot(d, T.GREEN).copy()
                tick = gfx.icon_image("", int(11 * k), "#FFFFFF")
                node.alpha_composite(tick, ((d - tick.width) // 2, (d - tick.height) // 2))
            elif current:
                node = gfx.dot(d, T.CARD, T.ORANGE, max(2, int(3 * k)))
                inner = gfx.dot(int(6 * k), T.ORANGE)
                node = node.copy()
                node.alpha_composite(inner, ((d - inner.width) // 2, (d - inner.height) // 2))
            else:
                node = gfx.dot(d, T.CARD, "#D3D7DD", max(1, int(1.5 * k)))
            img = gfx.tk_image(node)
            self._imgs.append(img)
            self.create_image(x, y, image=img, anchor="w")
            x += d + int(6 * k)
            font = T.F_SMALL_BOLD if current else T.F_SMALL
            self.create_text(x, y, text=s.name, font=font, anchor="w",
                             fill=T.INK if current or done else T.MUTED)
            x += tkfont.Font(font=font).measure(s.name) + int(10 * k)
            if i < len(stages) - 1:
                self.create_line(x, y, x + int(22 * k), y, width=max(1, int(1.5 * k)),
                                 fill=T.GREEN if done else "#D3D7DD")
                x += int(32 * k)
        self.configure(width=x)


class Segmented(tk.Frame):
    """Buttons side by side; the selected one is tinted orange (a 2-6 way choice, e.g. tabs of a sub-case)."""

    def __init__(self, parent, options, command, value=None):
        super().__init__(parent, bg=_bg_of(parent))
        self.command, self.btns = command, {}
        for i, opt in enumerate(options):
            b = RoundButton(self, opt, lambda o=opt: self.select(o), kind="soft", padx=12, height=30, font=T.F_SMALL_BOLD)
            b.grid(row=i // 8, column=i % 8, padx=(0, 4), pady=(0, 4), sticky="w")
            self.btns[opt] = b
        if options:
            self.select(value or options[0], fire=False)

    def select(self, opt, fire=True):
        for o, b in self.btns.items():
            b.kind = "tint" if o == opt else "soft"
            b._draw()
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


class RoundCard(tk.Canvas):
    """A rounded card. Put content in .inner (a Frame). fit=True: the card is as tall as its content.
    shadow: a soft shadow; border: a thin line around it."""

    def __init__(self, parent, fill=T.CARD, radius=18, pad=16, fit=False, shadow=True, border=False, **kw):
        k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, **kw)
        self.fill, self.radius, self.pad, self.fit = fill, int(radius * k), int(pad * k), fit
        self.border, self.m = border, int(5 * k) if shadow else 0
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window(self.pad + self.m, self.pad + self.m, window=self.inner, anchor="nw")
        self.bind("<Configure>", self._redraw)
        if fit:
            self.inner.bind("<Configure>", self._fit, add="+")

    def _fit(self, _e=None):
        h = self.inner.winfo_reqheight() + 2 * (self.pad + self.m)
        if int(self.cget("height")) != h:
            self.configure(height=h)

    def _redraw(self, _e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            return
        self.delete("shape")
        r = min(self.radius, (min(w, h) - 2 * self.m) // 2)
        if self.m or self.border:
            self._img = gfx.photo(w, h, r, self.fill, T.BORDER if self.border else None, shadow=self.m)
            self.create_image(0, 0, image=self._img, anchor="nw", tags="shape")
        else:  # large cards stay fast: four corner images and two rectangles
            self._img = gfx.corners(r, self.fill)
            for img, x, y, a in zip(self._img, (0, w, 0, w), (0, 0, h, h), ("nw", "ne", "sw", "se")):
                self.create_image(x, y, image=img, anchor=a, tags="shape")
            self.create_rectangle(r, 0, w - r, h, fill=self.fill, outline="", tags="shape")
            self.create_rectangle(0, r, w, h - r, fill=self.fill, outline="", tags="shape")
        self.tag_lower("shape")
        edge = self.pad + self.m
        self.itemconfigure(self._win, width=max(1, w - 2 * edge))
        if not self.fit:
            self.itemconfigure(self._win, height=max(1, h - 2 * edge))

    def recolor(self, fill):
        """New card colour (the inner frame and its direct plain children follow)."""
        old, self.fill = self.fill, fill
        self._redraw()
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
    """A menu entry on the dark shell: icon + label; the selected one is lighter, with a small orange bar."""

    def __init__(self, parent, icon, text, command, width=180, height=40, badge=False):
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
        w, h, k = self.winfo_width(), self.winfo_height(), self.k
        if w < 8:
            return
        self._imgs = []
        if self.selected or self.hover:
            self._imgs.append(gfx.photo(w, h, int(9 * k), T.SHELL_ACTIVE if self.selected else T.SHELL_HOVER))
            self.create_image(0, 0, image=self._imgs[-1], anchor="nw")
        if self.selected:
            t = max(3, int(3 * k))
            self._imgs.append(gfx.photo(t, int(18 * k), t // 2 + 1, T.ORANGE))
            self.create_image(int(2 * k), h // 2, image=self._imgs[-1], anchor="w")
        fg = "#FFFFFF" if self.selected or self.hover else "#C2C7D0"
        self._imgs.append(gfx.icon(self.icon, int(18 * k), T.ORANGE if self.selected else fg))
        self.create_image(int(14 * k), h // 2, image=self._imgs[-1], anchor="w")
        self.create_text(int(44 * k), h // 2, text=self.text, font=T.F_BOLD if self.selected else T.F_BODY,
                         fill=fg, anchor="w")
        if self.badge:  # small orange dot: something new (an update)
            self._imgs.append(gfx.tk_image(gfx.dot(int(8 * k), T.ORANGE), ("dot", int(8 * k), T.ORANGE)))
            self.create_image(w - int(14 * k), h // 2, image=self._imgs[-1], anchor="e")


class Pill(tk.Canvas):
    """Status pill on the dark shell: coloured dot + short text."""

    def __init__(self, parent, width=170, height=34):
        self.k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, width=int(width * self.k),
                         height=int(height * self.k))
        self.text, self.color = "Starting...", T.SHELL_MUTED
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, text, color):
        self.text, self.color = text[:60], color
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h, k = self.winfo_width(), self.winfo_height(), self.k
        if w < 8:
            return
        d = int(8 * k)
        self._imgs = [gfx.photo(w, h, h // 2, T.SHELL_HOVER), gfx.tk_image(gfx.dot(d, self.color), ("dot", d, self.color))]
        self.create_image(0, 0, image=self._imgs[0], anchor="nw")
        self.create_image(int(13 * k), h // 2, image=self._imgs[1], anchor="w")
        text = self.text
        f = tkfont.Font(font=T.F_SMALL)
        while text and f.measure(text) > w - int(44 * k):
            text = text[:-2]
        if text != self.text:
            text = text.rstrip() + "…"
        self.create_text(int(29 * k), h // 2, text=text, font=T.F_SMALL, fill=T.SHELL_TEXT, anchor="w")


# key-figure card colours: variant -> (card, caption, value)
_KPI = {"plain": (T.CARD, T.MUTED, T.INK), "dark": (T.DARK, "#AEB4BF", "white"),
        "accent": (T.ORANGE, "#FFF0E3", "white")}


class StatusCard(RoundCard):
    """A key figure: small caption, big value. variant: plain (white), dark or accent (orange)."""

    def __init__(self, parent, caption, value="—", variant="plain"):
        card, cap, val = _KPI[variant]
        super().__init__(parent, fill=card, radius=14, pad=11, fit=True, border=variant == "plain")
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
        being cut. Never taller than a one-line 20 pt value, so that the cards of a row stay the same height."""
        room = self.winfo_width() - 2 * (self.pad + self.m) - 8
        if room <= 0:
            return
        text = getattr(self, "value", self.val.cget("text"))
        cut = max(text.find("-"), text.find(" "))
        options = [(text, s) for s in (20, 17, 15, 13, 12)]
        if cut > 0:  # two lines, split after the hyphen / at the space
            two = text[:cut + 1].rstrip() + "\n" + text[cut + 1:].lstrip()
            options += [(two, s) for s in (11, 10)]
        options += [(text, s) for s in (11, 10, 9)]
        for shown, size in options:
            f = tkfont.Font(family=T.FONT_HEAD, size=size)
            if max(f.measure(line) for line in shown.split("\n")) <= room:
                break
        self.val.configure(text=shown, font=(T.FONT_HEAD, size), justify="left")


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
        tk.Label(self.tip, text=self.text, bg=T.DARK, fg="white", font=T.F_SMALL, padx=10, pady=5).pack()
        self.tip.update_idletasks()
        x = w.winfo_rootx() + w.winfo_width() // 2 - self.tip.winfo_reqwidth() // 2
        self.tip.geometry(f"+{x}+{w.winfo_rooty() + w.winfo_height() + 6}")
        gfx.window_frame(self.tip)

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class IconButton(tk.Canvas):
    """A square icon button with a tooltip; configure(state="disabled") greys it out."""

    def __init__(self, parent, icon, tip, command, size=36):
        self.k = _scale(parent)
        self.icon, self._command, self._state, self.hover = icon, command, "normal", False
        side = int(size * self.k)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, width=side, height=side, cursor="hand2")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._over(True), add="+")
        self.bind("<Leave>", lambda e: self._over(False), add="+")
        self.bind("<Button-1>", lambda e: self._state == "normal" and self._command())
        Tooltip(self, tip)

    def _over(self, on):
        self.hover = on
        self._draw()

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            tk.Canvas.configure(self, cursor="hand2" if self._state == "normal" else "")
            self._draw()
        return tk.Canvas.configure(self, cnf, **kw) if cnf or kw else None

    config = configure

    def _draw(self):
        self.delete("all")
        w, h, k = self.winfo_width(), self.winfo_height(), self.k
        if w < 8:
            return
        on = self._state == "normal"
        fill = T.BUTTON_HOVER if self.hover and on else T.BUTTON
        self._imgs = [gfx.photo(w, h, int(9 * k), fill, T.BUTTON_BORDER if on else T.LINE),
                      gfx.icon(self.icon, int(17 * k), T.INK if on else "#B4B9C2")]
        self.create_image(0, 0, image=self._imgs[0], anchor="nw")
        self.create_image(w // 2, h // 2, image=self._imgs[1])


class GradientTile(tk.Canvas):
    """A dashboard key figure on a rounded gradient tile: caption, big value, small note, and an icon."""

    def __init__(self, parent, caption, colors, value="—", note="", height=108, icon=""):
        k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, height=int(height * k))
        self.k, self.caption, self.colors, self.value, self.note, self.icon = k, caption, colors, value, note, icon
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value, note=""):
        self.value, self.note = value, note
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h, k = self.winfo_width(), self.winfo_height(), self.k
        if w < 20:
            return
        pad = int(14 * k)
        self._imgs = [gfx.tk_image(gfx.gradient(w, h, int(14 * k), *self.colors), ("g", w, h, self.colors))]
        self.create_image(0, 0, image=self._imgs[0], anchor="nw")
        room = w - 2 * pad
        side = int(18 * k)
        if self.icon and tkfont.Font(font=T.F_SMALL_BOLD).measure(self.caption) + side + int(6 * k) <= room:
            self._imgs.append(gfx.icon(self.icon, side, "#FFFFFF"))
            self.create_image(w - pad, pad, image=self._imgs[-1], anchor="ne")
        self.create_text(pad, pad, text=self.caption, fill="#FFFFFF", font=T.F_SMALL_BOLD, anchor="nw")
        for size in (22, 18, 15, 12):
            f = tkfont.Font(family=T.FONT_HEAD, size=size)
            if f.measure(self.value) <= room:
                break
        self.create_text(pad, h // 2 + int(4 * k), text=self.value, fill="#FFFFFF", font=(T.FONT_HEAD, size), anchor="w")
        if self.note:
            self.create_text(pad, h - int(11 * k), text=self.note, fill="#F4F7FF", font=T.F_SMALL, anchor="sw")


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
        self._imgs = []
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20:
            return
        k = self.k
        if not self.data:
            self.create_text(w // 2, h // 2, text="No data yet: open an order", fill=T.SUBTLE, font=T.F_SMALL)
            return
        top, bottom, left = int(18 * k), int(26 * k), int(26 * k)
        peak = max(v for _, v, _ in self.data) or 1
        step = max(1, -(-peak // 4))
        scale = max(peak, step * 4)
        for i in range(5):  # grid lines with their value
            y = int(h - bottom - (h - bottom - top) * (i * step) / scale)
            self.create_line(left, y, w, y, fill=T.LINE)
            self.create_text(left - 6, y, text=str(i * step), fill=T.SUBTLE, font=(T.FONT, 8), anchor="e")
        slot = (w - left) / len(self.data)
        bar = int(min(slot * 0.5, 44 * k))
        f = tkfont.Font(font=(T.FONT, 8))
        base = h - bottom
        for i, (label, value, color) in enumerate(self.data):
            x = int(left + slot * i + (slot - bar) / 2)
            y = int(base - (base - top) * value / scale)
            if value and base - y >= 1:
                self._imgs.append(gfx.tk_image(gfx.bar(bar, base - y, min(bar // 2, int(6 * k), base - y), color),
                                               ("b", bar, base - y, color)))
                self.create_image(x, y, image=self._imgs[-1], anchor="nw")
            self.create_text(x + bar // 2, y - 3, text=str(value), fill=T.INK, font=T.F_SMALL_BOLD, anchor="s")
            text = label
            while text and f.measure(text) > slot - 6:
                text = text[:-2]
            if text != label:
                text = text.rstrip() + "…"
            self.create_text(x + bar // 2, base + int(6 * k), text=text, fill=T.MUTED, font=(T.FONT, 8), anchor="n")


AI_A, AI_B, AI_TINT = "#7C5CFF", "#1FB6E8", "#F1EEFF"  # the bot's violet and cyan (see bot_kit)


class RoundButton(tk.Canvas):
    """A rounded button. kind: accent (orange), dark, soft, tint, ai (the bot's gradient), ai_soft. icon: a glyph
    before the text.
    configure(state=..., text=...) like a ttk button."""

    # kind -> (colour, hover colour, text colour, outline)
    _COLORS = {"accent": (T.ORANGE, T.ORANGE_DARK, "white", None), "dark": (T.DARK, T.DARK_SOFT, "white", None),
               "soft": (T.BUTTON, T.BUTTON_HOVER, T.INK, T.BUTTON_BORDER),
               "tint": (T.ORANGE_TINT, T.ORANGE_SOFT, T.ORANGE_DARK, None),
               "ai": (AI_A, AI_B, "white", None), "ai_soft": (AI_TINT, gfx.mix(AI_A, "#FFFFFF", 0.8), AI_A, None)}

    def __init__(self, parent, text, command, kind="accent", padx=18, height=36, font=None, icon=""):
        self.k = _scale(parent)
        self.text, self.command, self.kind, self.padx, self.icon = text, command, kind, padx, icon
        self.font = font or T.F_BOLD
        self.state, self.hover, self.down = "normal", False, False
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, height=int(height * self.k),
                         width=self._width(), cursor="hand2")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", lambda e: self._press(True))
        self.bind("<ButtonRelease-1>", self._release)

    def _width(self):
        extra = int(24 * self.k) if self.icon else 0
        return int(tkfont.Font(font=self.font).measure(self.text) + 2 * self.padx * self.k) + extra

    def _hover(self, on):
        self.hover = on
        self._draw()

    def _press(self, on):
        self.down = on
        self._draw()

    def _release(self, e):
        self._press(False)
        if self.state == "normal" and 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.command()

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
        w, h, k = self.winfo_width(), self.winfo_height(), self.k
        if w < 8:
            return
        base, hover, fg, line = self._COLORS[self.kind]
        fill = hover if self.hover and self.state == "normal" else base
        if self.state != "normal":
            fill, fg, line = ("#F9CBA3", "white", None) if self.kind == "accent" else (T.FIELD, "#A0A6B0", T.LINE)
        elif self.down:
            fill = gfx.mix(fill, "#000000", 0.08)
        if self.kind == "ai" and self.state == "normal":
            pair = (hover, base) if self.hover else (base, hover)
            self._imgs = [gfx.tk_image(gfx.gradient(w, h, int(10 * k), *pair), ("g", w, h, pair))]
        else:
            self._imgs = [gfx.photo(w, h, int(10 * k), fill, line)]
        self.create_image(0, 0, image=self._imgs[0], anchor="nw")
        cx = w // 2
        if self.icon:
            self._imgs.append(gfx.icon(self.icon, int(16 * k), fg))
            tw = tkfont.Font(font=self.font).measure(self.text)
            cx += int(11 * k)
            self.create_image(cx - tw // 2 - int(8 * k), h // 2, image=self._imgs[-1], anchor="e")
        self.create_text(cx, h // 2, text=self.text, fill=fg, font=self.font)
        tk.Canvas.configure(self, cursor="hand2" if self.state == "normal" else "")


class RoundEntry(tk.Canvas):
    """A rounded text field (orange outline when focused), with a grey hint while empty and an optional icon.
    .entry is the tk.Entry inside; get / insert / delete / bind / focus_set go to it, so it replaces a ttk.Entry."""

    def __init__(self, parent, textvariable=None, width=200, height=38, font=None, show="", placeholder="", icon=""):
        self.k = k = _scale(parent)
        super().__init__(parent, bg=_bg_of(parent), highlightthickness=0, bd=0, width=int(width * k),
                         height=int(height * k))
        self.focused, self.icon = False, icon
        font = font or (T.FONT, 10)
        self.entry = tk.Entry(self, textvariable=textvariable, bd=0, relief="flat", bg=T.FIELD, fg=T.INK, font=font,
                              insertbackground=T.INK, highlightthickness=0, show=show, selectbackground=T.ORANGE_SOFT,
                              selectforeground=T.INK)
        self._win = self.create_window(0, 0, window=self.entry, anchor="w")
        self.hint = None
        if placeholder:
            self.hint = tk.Label(self.entry, text=placeholder, bg=T.FIELD, fg=T.SUBTLE, font=font, bd=0, padx=0, pady=0,
                                 cursor="xterm")
            self.hint.bind("<Button-1>", lambda e: self.entry.focus_set())
            self.entry.bind("<KeyRelease>", lambda e: self._show_hint(), add="+")
            if textvariable is not None:
                textvariable.trace_add("write", lambda *_a: self._show_hint())
        self.entry.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        tk.Canvas.bind(self, "<Configure>", lambda e: self._draw())
        tk.Canvas.bind(self, "<Button-1>", lambda e: self.entry.focus_set())

    def _show_hint(self):
        if self.hint is None:
            return
        if self.entry.get() or self.focused:
            self.hint.place_forget()
        else:
            self.hint.place(x=1, rely=0.5, anchor="w")

    def _focus(self, on):
        self.focused = on
        self._draw()

    def _draw(self):
        tk.Canvas.delete(self, "shape")
        w, h, k = self.winfo_width(), self.winfo_height(), self.k
        if w < 8:
            return
        r = int(9 * k)
        fill = T.CARD if self.focused else T.FIELD
        self._imgs = [gfx.photo(w, h, r, fill, T.ORANGE if self.focused else T.BORDER,
                                line=max(1, int(1.5 * k)) if self.focused else 1)]
        self.create_image(0, 0, image=self._imgs[0], anchor="nw", tags="shape")
        left = int(12 * k)
        if self.icon:
            self._imgs.append(gfx.icon(self.icon, int(15 * k), T.MUTED))
            self.create_image(left, h // 2, image=self._imgs[-1], anchor="w", tags="shape")
            left += int(23 * k)
        self.tag_lower("shape")
        self.entry.configure(bg=fill)
        if self.hint is not None:
            self.hint.configure(bg=fill)
        self.coords(self._win, left, h // 2)
        self.itemconfigure(self._win, width=max(10, w - left - int(12 * k)))
        self._show_hint()

    def get(self):
        return self.entry.get()

    def delete(self, *args):
        self.entry.delete(*args)
        self._show_hint()

    def insert(self, *args):
        self.entry.insert(*args)
        self._show_hint()

    def bind(self, seq=None, func=None, add=None):
        return self.entry.bind(seq, func, add)

    def focus_set(self):
        self.entry.focus_set()
