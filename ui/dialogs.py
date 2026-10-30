"""SALTO Buddy-styled windows and messages, used instead of the plain Windows ones.

shell() is the frame of every SALTO Buddy window (logo + title, rounded card, button bar).
showinfo / showwarning / showerror / askyesno keep tkinter.messagebox's signature, so a module can simply
`from ui import dialogs as messagebox`.
"""
import os
import sys
import tkinter as tk

from salto.version import APP_NAME

from . import theme as T
from . import gfx
from .widgets import RoundButton, RoundCard, _scale

_ASSETS = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "assets")
_images = {}


def logo(widget, base=40):
    """The SALTO Buddy logo as a PhotoImage sized for the screen scaling (kept alive here)."""
    k = _scale(widget)
    px = min((40, 48, 64), key=lambda p: abs(p - base * k))  # the sizes bundled with the app
    key = (str(widget.winfo_toplevel()), px)
    if key not in _images:
        path = os.path.join(_ASSETS, f"logo_{px}.png")
        if not os.path.exists(path):
            return None
        _images[key] = tk.PhotoImage(master=widget, file=path)
    return _images[key]


def _root(parent):
    if parent is not None:
        return parent.winfo_toplevel()
    return tk._default_root


def shell(parent, title, subtitle="", width=560, height=None, modal=True, resizable=False):
    """A SALTO Buddy window: (window, body, footer). Put content in body, buttons in footer (packed right)."""
    owner = _root(parent)
    w = tk.Toplevel(owner)
    w.title(APP_NAME if title == APP_NAME else f"{APP_NAME} - {title}")
    w.configure(bg=T.CANVAS)
    w.resizable(resizable, resizable)
    if owner is not None and owner.winfo_viewable():
        w.transient(owner)
    w.bind("<Escape>", lambda e: w.destroy())
    k = _scale(w)
    head = tk.Frame(w, bg=T.CANVAS)
    head.pack(fill="x", padx=20, pady=(18, 10))
    img = logo(w, 40)
    if img:
        tk.Label(head, image=img, bg=T.CANVAS).pack(side="left", padx=(0, 12))
    names = tk.Frame(head, bg=T.CANVAS)
    names.pack(side="left", fill="x", expand=True)
    tk.Label(names, text=title, bg=T.CANVAS, fg=T.INK, font=T.F_TITLE, anchor="w").pack(fill="x")
    if subtitle:
        tk.Label(names, text=subtitle, bg=T.CANVAS, fg=T.MUTED, font=T.F_SMALL, anchor="w", justify="left",
                 wraplength=int((width - 120) * k)).pack(fill="x")
    foot = tk.Frame(w, bg=T.CANVAS)
    foot.pack(side="bottom", fill="x", padx=20, pady=(4, 16))
    card = RoundCard(w, radius=14, pad=16, fit=not height, border=True)  # fit: as tall as its content
    card.pack(fill="both", expand=True, padx=20, pady=(0, 8))
    w.update_idletasks()
    ww, hh = int(width * k), int(height * k) if height else None
    if owner is not None and owner.winfo_viewable():
        x = owner.winfo_rootx() + (owner.winfo_width() - ww) // 2
        y = owner.winfo_rooty() + max(40, (owner.winfo_height() - (hh or 300)) // 3)
    else:
        x, y = (w.winfo_screenwidth() - ww) // 2, w.winfo_screenheight() // 4
    w.geometry(f"{ww}x{hh}+{max(0, x)}+{max(0, y)}" if hh else f"{ww}x1+{max(0, x)}+{max(0, y)}")
    w.minsize(ww, 1)  # never narrower than asked: wrapped text is sized for this width
    if not hh:  # height from the content, once it is there
        w.after_idle(lambda: (w.geometry(""), w.after(30, lambda: _keep_on_screen(w))))
    if modal:
        w.after_idle(lambda: _grab(w))
    w.after_idle(lambda: gfx.window_frame(w, T.CANVAS, T.INK))
    return w, card.inner, foot


def _keep_on_screen(w):
    """Move a window up if its bottom would be under the taskbar."""
    try:
        w.update_idletasks()
        h, y = w.winfo_height(), w.winfo_y()
        limit = w.winfo_screenheight() - int(56 * _scale(w))
        if y + h > limit:
            w.geometry(f"+{w.winfo_x()}+{max(0, limit - h)}")
    except tk.TclError:
        pass


def _grab(w):
    try:
        w.grab_set()
        w.focus_force()
    except tk.TclError:
        pass


# kind -> (badge text, badge colour)
_KINDS = {"info": ("i", T.ORANGE), "warning": ("!", "#E0A100"), "error": ("!", T.RED), "question": ("?", T.DARK)}


def _message(kind, title, message, parent=None, buttons=(("OK", True),), default=0):
    result = {"value": None}
    w, body, foot = shell(parent, title or APP_NAME, width=480)
    row = tk.Frame(body, bg=T.CARD)
    row.pack(fill="both", expand=True)
    mark, color = _KINDS[kind]
    k = _scale(w)
    size = int(34 * k)
    badge = tk.Canvas(row, width=size, height=size, bg=T.CARD, highlightthickness=0)
    badge.image = gfx.tk_image(gfx.dot(size, color))
    badge.create_image(0, 0, image=badge.image, anchor="nw")
    badge.create_text(size // 2, size // 2, text=mark, fill="white", font=(T.FONT_SEMI, 13))
    badge.pack(side="left", anchor="n", padx=(0, 14))
    tk.Label(row, text=str(message), bg=T.CARD, fg=T.INK, font=T.F_BODY, justify="left", anchor="w",
             wraplength=int(360 * k)).pack(side="left", fill="x", expand=True, anchor="n")

    def pick(value):
        result["value"] = value
        w.destroy()

    for i, (text, value) in reversed(list(enumerate(buttons))):
        b = RoundButton(foot, text, lambda v=value: pick(v), kind="accent" if i == default else "soft")
        b.pack(side="right", padx=(8, 0))
        if i == default:
            w.bind("<Return>", lambda e, v=value: pick(v))
    w.protocol("WM_DELETE_WINDOW", lambda: pick(buttons[-1][1] if len(buttons) > 1 else buttons[0][1]))
    w.wait_window()
    return result["value"]


def showinfo(title=None, message="", parent=None, **_):
    _message("info", title, message, parent)
    return "ok"


def showwarning(title=None, message="", parent=None, **_):
    _message("warning", title, message, parent)
    return "ok"


def showerror(title=None, message="", parent=None, **_):
    _message("error", title, message, parent)
    return "ok"


def askyesno(title=None, message="", parent=None, **_):
    return bool(_message("question", title, message, parent, buttons=(("Yes", True), ("No", False))))
