"""Flat widgets: tables, a wrapping detail view, status cards, stage stepper, status pill."""
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
class StatusCard(tk.Frame):
    def __init__(self, parent, caption, value="—"):
        super().__init__(parent, bg=T.STATUS_CARD, highlightthickness=1, highlightbackground=T.LINE)
        self.cap = tk.Label(self, text=caption.upper(), bg=T.STATUS_CARD, fg=T.MUTED, font=T.F_CAPS, anchor="w")
        self.cap.pack(fill="x", padx=10, pady=(5, 0))
        self.val = tk.Label(self, text=value, bg=T.STATUS_CARD, fg=T.INK, font=T.F_BIG, anchor="w")
        self.val.pack(fill="x", padx=10, pady=(0, 5))
        self.bind("<Configure>", lambda e: self._fit())

    def set(self, value, rag=None):
        fg, bg = T.RAG.get(rag, (T.INK, T.STATUS_CARD)) if rag else (T.INK, T.STATUS_CARD)
        for w in (self, self.cap, self.val):
            w.configure(bg=bg)
        self.val.configure(text=value or "—", fg=fg)
        self._fit()

    def _fit(self):
        """Largest font (16 -> 9 pt) that fits the card, so long values shrink instead of being cut."""
        room = self.winfo_width() - 24
        if room <= 0:
            return
        text = self.val.cget("text")
        for size in (15, 13, 12, 11, 10, 9):
            f = tkfont.Font(family=T.FONT, size=size, weight="bold")
            if f.measure(text) <= room:
                break
        self.val.configure(font=(T.FONT, size, "bold"))


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
    """Buttons side by side; the selected one is orange (a 2-6 way choice, e.g. tabs of a sub-case)."""

    def __init__(self, parent, options, command, value=None):
        super().__init__(parent, bg=T.CARD)
        self.command, self.btns = command, {}
        for i, opt in enumerate(options):
            b = tk.Label(self, text=opt, font=T.F_SMALL_BOLD, padx=12, pady=5, cursor="hand2",
                         bg=T.BUTTON, fg=T.INK, highlightthickness=1, highlightbackground=T.BUTTON_BORDER)
            b.grid(row=i // 8, column=i % 8, padx=(0, 4), pady=(0, 4), sticky="w")
            b.bind("<Button-1>", lambda e, o=opt: self.select(o))
            b.bind("<Enter>", lambda e, b=b: b.cget("bg") != T.ORANGE and b.configure(bg=T.ORANGE_SOFT))
            b.bind("<Leave>", lambda e, b=b: b.cget("bg") != T.ORANGE and b.configure(bg=T.BUTTON))
            self.btns[opt] = b
        if options:
            self.select(value or options[0], fire=False)

    def select(self, opt, fire=True):
        for o, b in self.btns.items():
            on = o == opt
            b.configure(bg=T.ORANGE if on else T.BUTTON, fg="white" if on else T.INK,
                        highlightbackground=T.ORANGE if on else T.BUTTON_BORDER)
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


class Pill(tk.Frame):
    """Header status pill: coloured dot + text."""

    def __init__(self, parent):
        super().__init__(parent, bg=T.HEADER_HOVER, padx=10, pady=3)
        self.dot = tk.Label(self, text="●", bg=T.HEADER_HOVER, fg=T.PILL_READY, font=T.F_BODY)
        self.dot.pack(side="left")
        self.lbl = tk.Label(self, text="Ready", bg=T.HEADER_HOVER, fg="white", font=T.F_SMALL)
        self.lbl.pack(side="left", padx=(4, 0))

    def set(self, text, color):
        self.dot.configure(fg=color)
        self.lbl.configure(text=text[:60])
