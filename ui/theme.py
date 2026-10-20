"""Design tokens and ttk styling (flat 'black header, white cards, orange accent' system)."""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

ORANGE, ORANGE_DARK, ORANGE_SOFT, ORANGE_TINT = "#FF7900", "#E06A00", "#FFE8D6", "#FFF4EB"
HEADER, HEADER_HOVER, HEADER_BORDER = "#111111", "#2A2A2A", "#3A3A3A"
INK, MUTED, SUBTLE = "#1F2328", "#6B7280", "#9CA3AF"
CANVAS, CARD, LINE = "#F3F4F6", "#FFFFFF", "#E2E4E8"
BUTTON, BUTTON_BORDER, BUTTON_HOVER = "#F6F7F9", "#CFD3D9", "#ECEEF1"
ZEBRA, HEADING_BG, STATUS_CARD = "#FAFAFB", "#F7F7F8", "#F7F7F8"
GREEN, RED = "#1E7B34", "#C62828"
BLUE, BLUE_BG = "#1F6FB2", "#E3F0FB"
PILL_READY, PILL_OFFLINE = "#7BD88F", "#FF8A80"
RAG = {"green": (GREEN, "#E4F4E8"), "amber": ("#A15C00", "#FFF3D6"), "red": (RED, "#FDE7E7"),
       "grey": ("#595959", "#EFEFEF"), "blue": (BLUE, BLUE_BG)}

FONT, MONO = "Segoe UI", "Consolas"
F_BODY = (FONT, 10)
F_BOLD = (FONT, 10, "bold")
F_SMALL = (FONT, 9)
F_SMALL_BOLD = (FONT, 9, "bold")
F_CAPS = (FONT, 8, "bold")
F_SECTION = (FONT, 11, "bold")
F_TITLE = (FONT, 13, "bold")
F_APP = (FONT, 15, "bold")
F_BIG = (FONT, 16, "bold")
F_LOG = (MONO, 9)


def setup(root: tk.Tk):
    root.configure(bg=CANVAS)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        with _quiet():
            tkfont.nametofont(name).configure(family=FONT, size=10)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", font=F_BODY, background=CARD, foreground=INK, bordercolor=LINE, lightcolor=CARD,
                darkcolor=CARD, troughcolor=CANVAS, focuscolor=ORANGE)
    s.configure("Canvas.TFrame", background=CANVAS)
    s.configure("Card.TFrame", background=CARD)
    s.configure("Status.TFrame", background=STATUS_CARD)
    s.configure("TLabel", background=CARD, foreground=INK)
    s.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=F_SMALL)
    s.configure("Caps.TLabel", background=STATUS_CARD, foreground=MUTED, font=F_CAPS)
    s.configure("Title.TLabel", background=CARD, foreground=INK, font=F_TITLE)
    s.configure("Section.TLabel", background=CARD, foreground=ORANGE, font=F_SECTION)
    s.configure("Bar.TLabel", background=CARD, foreground=MUTED, font=F_SMALL)
    s.configure("Link.TLabel", background=CARD, foreground=ORANGE, font=F_SMALL_BOLD)

    # buttons
    s.configure("Accent.TButton", background=ORANGE, foreground="white", font=F_BOLD, borderwidth=0,
                padding=(16, 6), relief="flat")
    s.map("Accent.TButton", background=[("disabled", "#F7C49A"), ("pressed", ORANGE_DARK), ("active", ORANGE_DARK)],
          foreground=[("disabled", "white")])
    s.configure("TButton", background=BUTTON, foreground=INK, bordercolor=BUTTON_BORDER, borderwidth=1,
                padding=(12, 6), relief="flat", lightcolor=BUTTON, darkcolor=BUTTON, focusthickness=0)
    s.map("TButton", background=[("active", BUTTON_HOVER)], bordercolor=[("active", ORANGE)],
          foreground=[("disabled", "#A0A4AB")])
    s.configure("Header.TButton", background=HEADER, foreground="white", bordercolor=HEADER_BORDER,
                lightcolor=HEADER, darkcolor=HEADER, padding=(12, 5))
    s.map("Header.TButton", background=[("active", HEADER_HOVER)], bordercolor=[("active", ORANGE)])
    s.configure("Update.TButton", background=ORANGE, foreground="white", bordercolor=ORANGE,
                lightcolor=ORANGE, darkcolor=ORANGE, font=F_BOLD, padding=(12, 5))
    s.map("Update.TButton", background=[("active", ORANGE_DARK)])

    # inputs
    s.configure("TEntry", fieldbackground=CARD, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=6)
    s.map("TEntry", bordercolor=[("focus", ORANGE)], lightcolor=[("focus", ORANGE)])
    s.configure("TCheckbutton", background=CARD, foreground=INK, indicatorbackground=CARD,
                indicatorforeground="white", focuscolor=CARD)
    s.map("TCheckbutton", indicatorbackground=[("selected", ORANGE)], background=[("active", CARD)])

    # tabs
    s.configure("TNotebook", background=CANVAS, borderwidth=0, tabmargins=(16, 6, 16, 0))
    s.configure("TNotebook.Tab", background=CANVAS, foreground=MUTED, font=F_BOLD, padding=(16, 7), borderwidth=0)
    s.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ORANGE)],
          expand=[("selected", (0, 0, 0, 0))])
    s.configure("Inner.TNotebook", background=CARD, tabmargins=(0, 4, 0, 0))
    s.configure("Inner.TNotebook.Tab", background=HEADING_BG, foreground=MUTED, font=F_SMALL_BOLD, padding=(12, 5))
    s.map("Inner.TNotebook.Tab", background=[("selected", ORANGE)], foreground=[("selected", "white")])

    # tables
    s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=_px(root, 28),
                font=F_BODY, borderwidth=0, relief="flat")
    s.configure("Treeview.Heading", background=HEADING_BG, foreground=MUTED, font=F_SMALL_BOLD, relief="flat",
                borderwidth=0, padding=(6, 4))
    s.map("Treeview.Heading", background=[("active", BUTTON_HOVER)])
    s.map("Treeview", background=[("selected", ORANGE_SOFT)], foreground=[("selected", INK)])
    s.configure("Nav.Treeview", background=ZEBRA, fieldbackground=ZEBRA, rowheight=_px(root, 26), font=F_BODY)
    s.map("Nav.Treeview", background=[("selected", ORANGE)], foreground=[("selected", "white")])
    s.layout("Nav.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("TScrollbar", background=BUTTON, troughcolor=CARD, bordercolor=CARD, arrowcolor=MUTED,
                lightcolor=BUTTON, darkcolor=BUTTON, gripcount=0)
    s.configure("TPanedwindow", background=CARD)
    s.configure("Sash", sashthickness=6, background=LINE)
    s.configure("Horizontal.TProgressbar", background=ORANGE, troughcolor=LINE, bordercolor=LINE,
                lightcolor=ORANGE, darkcolor=ORANGE, thickness=3)


def _px(root, px):
    """Pixels at 96 dpi -> pixels on this screen (Treeview row heights are not DPI-scaled by Tk)."""
    return int(px * root.winfo_fpixels("1i") / 96)


class _quiet:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True
