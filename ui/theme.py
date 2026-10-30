"""Design tokens and ttk styling, in the style of Windows 11: a dark shell (title bar and menu) around a rounded
white sheet, Orange accent, soft shadows, Segoe UI Variable and Fluent icons. Falls back to Segoe UI on Windows 10.

ttk's own drawing is square and jagged, so its buttons, fields, check boxes, tabs and scroll bars are images made by
gfx. Those images sit on white: ttk widgets are only used on white cards."""
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import gfx

ORANGE, ORANGE_DARK, ORANGE_SOFT, ORANGE_TINT = "#FF7900", "#E86E00", "#FFE3CC", "#FFF3E8"
SHELL, SHELL_HOVER, SHELL_ACTIVE = "#15171C", "#22252C", "#2B2F38"   # title bar, menu, status line
SHELL_TEXT, SHELL_MUTED = "#ECEEF2", "#969DAA"
HEADER, HEADER_HOVER, HEADER_BORDER = SHELL, SHELL_HOVER, SHELL_ACTIVE
INK, MUTED, SUBTLE = "#17191E", "#5F6875", "#98A0AC"
CANVAS, CARD, LINE, BORDER = "#F3F4F6", "#FFFFFF", "#ECEEF1", "#E4E6EA"
DARK, DARK_SOFT, SHADOW = "#23262E", "#343843", "#E4E6EB"
NAV_HOVER, FIELD = "#F3F4F6", "#F6F7F9"
BUTTON, BUTTON_BORDER, BUTTON_HOVER = "#F6F7F9", "#DFE2E7", "#ECEEF1"
ZEBRA, HEADING_BG, STATUS_CARD = "#FBFBFC", "#FFFFFF", "#FFFFFF"
GREEN, RED = "#1B7F3B", "#C62828"
BLUE, BLUE_BG = "#1F6FB2", "#E5F1FB"
PILL_READY, PILL_OFFLINE = "#4ADE80", "#FF8A80"
RAG = {"green": (GREEN, "#E7F6EC"), "amber": ("#A15C00", "#FFF4DC"), "red": (RED, "#FDEAEA"),
       "grey": ("#5C6470", "#F0F1F3"), "blue": (BLUE, BLUE_BG)}

_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_W11 = os.path.exists(os.path.join(_FONTS, "SegUIVar.ttf"))
FONT = "Segoe UI Variable Text" if _W11 else "Segoe UI"
FONT_SEMI = "Segoe UI Variable Text Semibold" if _W11 else "Segoe UI Semibold"
FONT_HEAD = "Segoe UI Variable Display Semib" if _W11 else "Segoe UI Semibold"  # Windows cuts the name at 31 letters
MONO = "Consolas"
F_BODY = (FONT, 10)
F_BOLD = (FONT_SEMI, 10)
F_SMALL = (FONT, 9)
F_SMALL_BOLD = (FONT_SEMI, 9)
F_CAPS = (FONT_SEMI, 8)
F_SECTION = (FONT_HEAD, 12)
F_TITLE = (FONT_HEAD, 14)
F_APP = (FONT_HEAD, 15)
F_PAGE = (FONT_HEAD, 21)
F_KPI = (FONT_HEAD, 20)
F_BIG = (FONT_HEAD, 16)
F_LOG = (MONO, 9)
ICONS = "Segoe Fluent Icons" if os.path.exists(os.path.join(_FONTS, "SegoeIcons.ttf")) else "Segoe MDL2 Assets"
F_ICON = (ICONS, 13)

_keep = []  # ttk does not keep its element images alive


def _img(*args, **kw):
    im = gfx.photo(*args, **kw)
    _keep.append(im)
    return im


def _pil(image):
    im = gfx.tk_image(image)
    _keep.append(im)
    return im


def _button_style(s, name, k, normal, hover, pressed, disabled, outline=None):
    """A rounded button style from images. normal... are fill colours."""
    w, h, r = int(44 * k), int(34 * k), int(9 * k)
    elem = f"{name}.border"
    pic = lambda fill, line=outline: _img(w, h, r, fill, line, bg=CARD)
    s.element_create(elem, "image", pic(normal), ("disabled", pic(disabled, None)), ("pressed", pic(pressed)),
                     ("active", pic(hover)), border=int(11 * k), padding=0, sticky="nsew")
    s.layout(f"{name}.TButton" if name != "Soft" else "TButton",
             [(elem, {"sticky": "nsew", "children": [("Button.padding", {"sticky": "nsew", "children": [
                 ("Button.label", {"sticky": "nsew"})]})]})])


def _fluent(s, root):
    k = root.winfo_fpixels("1i") / 96

    # buttons
    _button_style(s, "Soft", k, BUTTON, BUTTON_HOVER, BORDER, FIELD, BUTTON_BORDER)
    _button_style(s, "Accent", k, ORANGE, ORANGE_DARK, "#D46400", "#F9CBA3")
    _button_style(s, "Dark", k, DARK, DARK_SOFT, SHELL, "#AEB3BC")
    _button_style(s, "Header", k, DARK, DARK_SOFT, SHELL, "#AEB3BC")
    _button_style(s, "Update", k, ORANGE, ORANGE_DARK, "#D46400", "#F9CBA3")
    pad = (int(14 * k), int(6 * k))
    s.configure("TButton", padding=pad, background=CARD, foreground=INK, font=F_BODY, anchor="center")
    s.map("TButton", foreground=[("disabled", "#A0A6B0")], background=[("active", CARD)])
    for name in ("Accent", "Dark", "Header", "Update"):
        s.configure(f"{name}.TButton", padding=pad, background=CARD, foreground="white", font=F_BOLD, anchor="center")
        s.map(f"{name}.TButton", foreground=[("disabled", "white")], background=[("active", CARD)])

    # text fields and the drop-down
    w, h, r = int(44 * k), int(34 * k), int(8 * k)
    field = lambda fill, line, width=1: _img(w, h, r, fill, line, line=width, bg=CARD)
    s.element_create("Fluent.field", "image", field(FIELD, BORDER), ("focus", field(CARD, ORANGE, max(1, int(1.5 * k)))),
                     ("disabled", field(CANVAS, LINE)), ("active", field(FIELD, BUTTON_BORDER)),
                     border=int(10 * k), padding=0, sticky="nsew")
    s.layout("TEntry", [("Fluent.field", {"sticky": "nsew", "children": [("Entry.padding", {
        "sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})]})])
    s.configure("TEntry", padding=(int(10 * k), int(7 * k)), foreground=INK, selectbackground=ORANGE_SOFT,
                selectforeground=INK, insertcolor=INK, background=CARD)
    chevron = gfx.icon("\uE70D", int(11 * k), MUTED)
    _keep.append(chevron)
    s.element_create("Fluent.downarrow", "image", chevron, padding=(int(6 * k), 0, int(10 * k), 0), sticky="")
    s.layout("TCombobox", [("Fluent.field", {"sticky": "nsew", "children": [
        ("Fluent.downarrow", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"expand": 1, "sticky": "nsew", "children": [("Combobox.textarea", {"sticky": "nsew"})]})]})])
    s.configure("TCombobox", padding=(int(10 * k), int(7 * k)), foreground=INK, background=CARD, arrowsize=0,
                selectbackground=FIELD, selectforeground=INK)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD)], selectbackground=[("readonly", FIELD)],
          selectforeground=[("readonly", INK)], background=[("readonly", CARD)])
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", ORANGE_TINT)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    root.option_add("*TCombobox*Listbox.font", F_BODY)
    root.option_add("*TCombobox*Listbox.relief", "flat")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    # check boxes, on a white card and on the grey window behind it
    d, r, gap = int(18 * k), int(5 * k), int(8 * k)
    mark = gfx.icon_image("\uE73E", int(12 * k), "#FFFFFF")
    for style, bg in (("TCheckbutton", CARD), ("Canvas.TCheckbutton", CANVAS)):
        def pic(fill, line=None, tick=False):
            im = gfx.rounded(d + gap, d, 0, bg).copy()
            im.alpha_composite(gfx.rounded(d, d, r, fill, line), (0, 0))
            if tick:
                im.alpha_composite(mark, ((d - mark.width) // 2, (d - mark.height) // 2))
            return _pil(im)
        elem = f"{style.split('.')[0]}.check" if bg == CANVAS else "Fluent.check"
        s.element_create(elem, "image", pic(CARD, "#8B929D"), ("selected", pic(ORANGE, tick=True)),
                         ("active", pic(ORANGE_TINT, ORANGE)), sticky="")
        s.layout(style, [("Checkbutton.padding", {"sticky": "nsew", "children": [
            (elem, {"side": "left", "sticky": ""}), ("Checkbutton.label", {"side": "left", "sticky": "nsew"})]})])
        s.configure(style, background=bg, foreground=INK, padding=(0, int(2 * k)))
        s.map(style, background=[("active", bg)])

    # tabs: text with an orange line under the selected one
    w, h = int(44 * k), int(36 * k)
    plain = gfx.rounded(w, h, 0, CARD)
    hover = gfx.rounded(w, h, int(7 * k), FIELD, bg=CARD)
    picked = plain.copy()
    t = max(2, int(3 * k))
    picked.alpha_composite(gfx.rounded(w - int(20 * k), t, t // 2 + 1, ORANGE), (int(10 * k), h - t))
    s.element_create("Line.tab", "image", _pil(plain), ("selected", _pil(picked)), ("active", _pil(hover)),
                     border=(int(14 * k), int(6 * k), int(14 * k), int(8 * k)), padding=0, sticky="nsew")
    s.layout("Inner.TNotebook.Tab", [("Line.tab", {"sticky": "nsew", "children": [("Notebook.padding", {
        "sticky": "nsew", "children": [("Notebook.label", {"sticky": ""})]})]})])
    s.configure("TNotebook", background=CARD, borderwidth=0, tabmargins=(0, 0, 0, 0))
    s.configure("Inner.TNotebook", background=CARD, borderwidth=0, tabmargins=(0, 2, 0, 4), bordercolor=CARD,
                lightcolor=CARD, darkcolor=CARD)
    s.configure("Inner.TNotebook.Tab", background=CARD, foreground=MUTED, font=F_BOLD,
                padding=(int(14 * k), int(7 * k), int(14 * k), int(9 * k)))
    pad = (int(14 * k), int(7 * k), int(14 * k), int(9 * k))
    s.map("Inner.TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", INK), ("active", INK)],
          padding=[("selected", pad)], expand=[("selected", (0, 0, 0, 0))])

    # scroll bars: a slim rounded thumb, no arrows
    long_, side = int(40 * k), int(12 * k)
    def thumb(thick, color, vertical):
        a, b = (side, long_) if vertical else (long_, side)
        base = gfx.rounded(a, b, 0, CARD).copy()
        x, y = (side - thick) // 2, int(2 * k)
        bar = gfx.rounded(thick, long_ - 2 * y, thick // 2, color) if vertical else \
            gfx.rounded(long_ - 2 * y, thick, thick // 2, color)
        base.alpha_composite(bar, (x, y) if vertical else (y, x))
        return _pil(base)
    thin, wide = max(3, int(4 * k)), max(5, int(7 * k))
    for tag, orient, vertical in (("FV", "Vertical", True), ("FH", "Horizontal", False)):
        s.element_create(f"{tag}.thumb", "image", thumb(thin, "#C9CDD4", vertical),
                         ("pressed", thumb(wide, "#8B929D", vertical)), ("active", thumb(wide, "#A4AAB4", vertical)),
                         border=(0, int(10 * k)) if vertical else (int(10 * k), 0), sticky="nsew")
        s.layout(f"{orient}.TScrollbar", [(f"{orient}.Scrollbar.trough", {"sticky": "nsew", "children": [
            (f"{tag}.thumb", {"expand": 1, "sticky": "nsew"})]})])
        s.configure(f"{orient}.TScrollbar", troughcolor=CARD, background=CARD, bordercolor=CARD, lightcolor=CARD,
                    darkcolor=CARD, arrowsize=side, relief="flat", borderwidth=0)

    # tables: no boxes, a thin line under the headings
    w, h = int(16 * k), int(30 * k)
    def head(fill):
        im = gfx.rounded(w, h, 0, fill).copy()
        im.paste(gfx.rgb(BORDER) + (255,), (0, h - 1, w, h))
        return _pil(im)
    s.element_create("Fluent.cell", "image", head(CARD), ("active", head(FIELD)), border=(2, 2, 2, 2), sticky="nsew")
    s.layout("Treeview.Heading", [("Fluent.cell", {"sticky": "nsew"}), ("Treeheading.padding", {"sticky": "nsew", "children": [
        ("Treeheading.image", {"side": "right", "sticky": ""}), ("Treeheading.text", {"sticky": "we"})]})])
    s.layout("Treeview", [("Treeview.padding", {"sticky": "nsew", "children": [("Treeview.treearea", {"sticky": "nsew"})]})])
    s.layout("Nav.Treeview", [("Treeview.treearea", {"sticky": "nsew"})])


def setup(root: tk.Tk):
    root.configure(bg=SHELL)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        with _quiet():
            tkfont.nametofont(name).configure(family=FONT, size=10)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", font=F_BODY, background=CARD, foreground=INK, bordercolor=LINE, lightcolor=CARD,
                darkcolor=CARD, troughcolor=CANVAS, focuscolor=CARD)
    s.configure("Canvas.TFrame", background=CANVAS)
    s.configure("Card.TFrame", background=CARD)
    s.configure("Status.TFrame", background=STATUS_CARD)
    s.configure("TLabel", background=CARD, foreground=INK)
    s.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=F_SMALL)
    s.configure("Caps.TLabel", background=STATUS_CARD, foreground=MUTED, font=F_CAPS)
    s.configure("Title.TLabel", background=CARD, foreground=INK, font=F_TITLE)
    s.configure("Section.TLabel", background=CARD, foreground=INK, font=F_SECTION)
    s.configure("Bar.TLabel", background=CARD, foreground=MUTED, font=F_SMALL)
    s.configure("Link.TLabel", background=CARD, foreground=ORANGE, font=F_SMALL_BOLD)
    _fluent(s, root)

    # tables
    s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=_px(root, 32),
                font=F_BODY, borderwidth=0, relief="flat", bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
    s.configure("Treeview.Heading", background=CARD, foreground=MUTED, font=F_SMALL_BOLD, relief="flat",
                borderwidth=0, padding=(_px(root, 8), _px(root, 7)))
    s.map("Treeview", background=[("selected", ORANGE_TINT)], foreground=[("selected", INK)])
    s.configure("Nav.Treeview", background=FIELD, fieldbackground=FIELD, rowheight=_px(root, 30), font=F_BODY)
    s.map("Nav.Treeview", background=[("selected", ORANGE_SOFT)], foreground=[("selected", INK)])
    s.configure("TPanedwindow", background=CARD)
    s.configure("Sash", sashthickness=6, background=LINE)
    s.configure("Horizontal.TProgressbar", background=ORANGE, troughcolor=LINE, bordercolor=LINE,
                lightcolor=ORANGE, darkcolor=ORANGE, thickness=4)


def _px(root, px):
    """Pixels at 96 dpi -> pixels on this screen (Treeview row heights are not DPI-scaled by Tk)."""
    return int(px * root.winfo_fpixels("1i") / 96)


class _quiet:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True
