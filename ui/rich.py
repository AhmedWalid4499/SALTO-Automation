"""Show Buddy's answers in a tk.Text: the small Markdown subset the assistant is asked to use.

Headings (#, ##, ###), bullets (- / *, two-space indent for a sub-level), numbered lists, **bold**,
`code`, tables (| a | b |) as real sortable tables, and a closing "Source: ..." line in muted text.
"""
import re
import tkinter as tk
from tkinter import ttk

from . import theme as T
from .widgets import Table

_INLINE = re.compile(r"(\*\*[^*\n]+\*\*|`[^`\n]+`)")
_BULLET = re.compile(r"^(\s*)[-*•]\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_HEADING = re.compile(r"^#{1,4}\s+(.*)$")
_RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")


def setup(text):
    """Tags used by render(); call once per Text widget."""
    text.tag_configure("md_body", lmargin1=8, lmargin2=8, rmargin=20, spacing1=1, spacing3=3)
    text.tag_configure("md_h", font=T.F_SECTION, foreground=T.INK, lmargin1=8, lmargin2=8, spacing1=10, spacing3=4)
    text.tag_configure("md_b1", lmargin1=14, lmargin2=30, rmargin=20, spacing1=1, spacing3=2)
    text.tag_configure("md_b2", lmargin1=34, lmargin2=50, rmargin=20, spacing1=1, spacing3=2)
    text.tag_configure("md_mark", foreground=T.ORANGE, font=T.F_BOLD)
    text.tag_configure("md_bold", font=T.F_BOLD)
    text.tag_configure("md_code", font=T.F_LOG, background=T.HEADING_BG)
    text.tag_configure("md_source", font=T.F_SMALL, foreground=T.MUTED, lmargin1=8, lmargin2=8, spacing1=6,
                       spacing3=2)
    text.tag_configure("md_gap", font=(T.FONT, 4))
    text.bind("<Configure>", lambda e: _fit_tables(text), add="+")


def render(text, md):
    """Append md at the end of text (which must be in state normal)."""
    lines = md.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.lstrip().startswith("|"):  # table: every following | line
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            _table(text, block)
            continue
        i += 1
        if not line.strip():
            text.insert("end", "\n", "md_gap")
            continue
        if _RULE.match(line):
            continue
        m = _HEADING.match(line)
        if m:
            _inline(text, m.group(1).strip("* "), "md_h")
            continue
        if re.match(r"^(source|sources)\s*:", line.strip(), re.I) or re.match(r"^_?source", line.strip(), re.I):
            text.insert("end", line.strip().strip("_*") + "\n", "md_source")
            continue
        m = _BULLET.match(line)
        if m:
            tag = "md_b2" if len(m.group(1)) >= 2 else "md_b1"
            text.insert("end", "•  " if tag == "md_b1" else "◦  ", (tag, "md_mark"))
            _inline(text, m.group(2), tag)
            continue
        m = _NUMBER.match(line)
        if m:
            tag = "md_b2" if len(m.group(1)) >= 2 else "md_b1"
            text.insert("end", f"{m.group(2)}.  ", (tag, "md_mark"))
            _inline(text, m.group(3), tag)
            continue
        _inline(text, line, "md_body")


def plain(md):
    """The answer as clean text for the clipboard: tables tab-separated (they paste as Excel columns), bullets as •."""
    out = []
    for line in md.strip().splitlines():
        s = line.rstrip()
        if s.lstrip().startswith("|"):
            if not re.fullmatch(r"\|?[\s:|-]+\|?", s.strip()):
                out.append("\t".join(_cells(s)))
            continue
        if _RULE.match(s):
            continue
        s = _HEADING.sub(r"\1", s)
        s = _BULLET.sub(lambda m: m.group(1) + "• " + m.group(2), s)
        out.append(re.sub(r"\*\*|`", "", s))
    return "\n".join(out)


def _inline(text, s, tag):
    for part in _INLINE.split(s):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            text.insert("end", part[2:-2], (tag, "md_bold"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            text.insert("end", part[1:-1], (tag, "md_code"))
        else:
            text.insert("end", part, (tag,))
    text.insert("end", "\n", (tag,))


def _cells(row):
    return [re.sub(r"\*\*|`", "", c).strip() for c in row.strip().strip("|").split("|")]


def _table(text, block):
    rows = [r for r in block if not re.fullmatch(r"\|?[\s:|-]+\|?", r)]  # drop the | --- | separator
    if not rows:
        return
    head = _cells(rows[0])
    head = [h or f"Column {k + 1}" for k, h in enumerate(head)]
    data = []
    for r in rows[1:]:
        c = _cells(r)
        data.append({h: (c[k] if k < len(c) else "") for k, h in enumerate(head)})
    shown = min(len(data), 12) or 1
    row_h = int(ttk.Style().lookup("Treeview", "rowheight") or 28)
    box = tk.Frame(text, bg=T.CARD, highlightthickness=1, highlightbackground=T.BORDER,
                   height=row_h * (shown + 1) + 8, width=_width(text))
    box.pack_propagate(False)
    Table(box, head, data, height=shown).pack(fill="both", expand=True)
    box._md_table = True
    text.insert("end", " ", "md_body")
    text.window_create("end", window=box, padx=8, pady=4)
    text.insert("end", "\n", "md_body")


def _width(text):
    return max(320, text.winfo_width() - 60)


def _fit_tables(text):
    w = _width(text)
    for name in text.window_names():
        box = text.nametowidget(name)
        if getattr(box, "_md_table", False) and int(box.cget("width")) != w:
            box.configure(width=w)
