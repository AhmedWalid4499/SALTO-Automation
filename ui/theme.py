"""Colours, fonts and ttk styling shared by the whole app."""
from tkinter import ttk

import customtkinter as ctk

ORANGE = "#FF7900"
ORANGE_HOVER = "#E56D00"
ORANGE_SOFT = "#FFF1E5"
BLUE = "#3EA9F5"
GREEN = "#40B44F"
GREY = "#E5E7EB"
INK = "#111827"
MUTED = "#6B7280"
BG = "#F5F6F8"
CARD = "#FFFFFF"
BORDER = "#E5E7EB"
SIDEBAR = "#16181D"
SIDEBAR_HOVER = "#262A33"
SIDEBAR_TEXT = "#D1D5DB"

FONT = "Segoe UI"


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def setup(root=None):
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    # ttk widgets do not follow CTk's DPI scaling: scale row heights ourselves
    k = ctk.ScalingTracker.get_widget_scaling(root) if root is not None else 1.0
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=int(32 * k),
                font=(FONT, 11), borderwidth=0, relief="flat")
    s.configure("Treeview.Heading", background="#F3F4F6", foreground=INK, font=(FONT, 11, "bold"),
                relief="flat", borderwidth=0, padding=(int(8 * k), int(6 * k)))
    s.map("Treeview.Heading", background=[("active", "#E5E7EB")])
    s.map("Treeview", background=[("selected", ORANGE_SOFT)], foreground=[("selected", INK)])
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no border
    s.configure("Vertical.TScrollbar", background=GREY, troughcolor=CARD, borderwidth=0, arrowsize=12)
    s.configure("Horizontal.TScrollbar", background=GREY, troughcolor=CARD, borderwidth=0, arrowsize=12)
