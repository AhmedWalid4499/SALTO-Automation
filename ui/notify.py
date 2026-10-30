"""'Task done' notifications: a SALTO Buddy card in the bottom-right corner of the screen (above the taskbar),
plus a taskbar flash when SALTO Buddy is not the active window. Settings: notify (on/off), notify_sound."""
import ctypes
import tkinter as tk
from ctypes import wintypes

from . import gfx
from . import theme as T
from .dialogs import logo
from .widgets import _scale

_open = []  # toasts on screen, stacked upwards


def _work_area():
    """(right, bottom) of the screen area above the taskbar."""
    rect = wintypes.RECT()
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        return rect.right, rect.bottom
    except Exception:
        return None


def _flash(root):
    """Flash the taskbar button until SALTO Buddy is brought to the front."""
    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)  # FLASHW_ALL | FLASHW_TIMERNOFG
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def app_active(root):
    try:
        return root.focus_displayof() is not None
    except (tk.TclError, KeyError):
        return False


def show(root, title, message, on_open=None, kind="done", seconds=9, sound=False):
    """One notification card. kind: done (green), error (red), info (orange)."""
    k = _scale(root)
    width = int(360 * k)
    t = tk.Toplevel(root)
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    t.configure(bg=T.CARD)
    # a plain window: Windows rounds its corners smoothly and gives it a shadow (see gfx.window_frame)
    card = tk.Frame(t, bg=T.CARD, padx=int(14 * k), pady=int(12 * k), highlightthickness=1,
                    highlightbackground=T.BORDER)
    card.pack(fill="both", expand=True)
    tk.Frame(card, bg=T.CARD, width=width - int(30 * k), height=0).pack()
    row = tk.Frame(card, bg=T.CARD)
    row.pack(fill="x")
    img = logo(t, 40)
    if img:
        tk.Label(row, image=img, bg=T.CARD).pack(side="left", anchor="n", padx=(0, 12))
    text = tk.Frame(row, bg=T.CARD)
    text.pack(side="left", fill="x", expand=True)
    color = {"done": T.GREEN, "error": T.RED}.get(kind, T.ORANGE)
    head = tk.Frame(text, bg=T.CARD)
    head.pack(fill="x")
    t.dot = gfx.tk_image(gfx.dot(int(8 * k), color))
    tk.Label(head, image=t.dot, bg=T.CARD).pack(side="left")
    tk.Label(head, text=title, bg=T.CARD, fg=T.INK, font=T.F_BOLD, anchor="w").pack(side="left", padx=(6, 0))
    t.x = gfx.icon("\uE711", int(12 * k), T.MUTED)
    close = tk.Label(head, image=t.x, bg=T.CARD, cursor="hand2")
    close.pack(side="right")
    tk.Label(text, text=message, bg=T.CARD, fg=T.MUTED, font=T.F_SMALL, anchor="w", justify="left",
             wraplength=width - int(110 * k)).pack(fill="x", pady=(2, 0))
    if on_open:
        link = tk.Label(text, text="Open", bg=T.CARD, fg=T.ORANGE, font=T.F_SMALL_BOLD, cursor="hand2", anchor="w")
        link.pack(anchor="w", pady=(6, 0))

    def dismiss(_e=None):
        if t in _open:
            _open.remove(t)
        t.destroy()
        _restack()

    def open_it(_e=None):
        dismiss()
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
        except tk.TclError:
            pass
        on_open()

    close.bind("<Button-1>", dismiss)
    if on_open:
        link.bind("<Button-1>", open_it)
        for w in (card, row, text):
            w.bind("<Button-1>", open_it)
    t.update_idletasks()
    _open.append(t)
    _restack()
    gfx.window_frame(t)
    t.after(seconds * 1000, lambda: t.winfo_exists() and dismiss())
    if not app_active(root):
        _flash(root)
    if sound:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
    return t


def _restack():
    """Newest at the bottom right, older ones above it."""
    area = None
    y = None
    for t in reversed(_open):
        if not t.winfo_exists():
            continue
        if area is None:
            area = _work_area() or (t.winfo_screenwidth(), t.winfo_screenheight() - 48)
            y = area[1] - 12
        t.update_idletasks()
        w, h = t.winfo_reqwidth(), t.winfo_reqheight()
        y -= h
        t.geometry(f"+{area[0] - w - 16}+{y}")
        y -= 8
