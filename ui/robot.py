"""The Friendly SALTO Bot: our robot mascot, drawn on a canvas so it is sharp at any size and can move.

Robot(parent, size): floats up and down, blinks now and then; set_mode("thinking") makes it bob faster with its
antenna glowing and its eyes looking around; set_mode("idle") brings it back. animate=False: a still avatar.
"""
import math
import tkinter as tk

from . import theme as T

HEAD_TOP, HEAD_BOTTOM = "#D6E8FB", "#A8C8EF"
TRIM, VISOR, EYES, SHADOW = "#8DABD3", "#0B0F14", "#14A6F5", "#DCE9FA"


def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


class Robot(tk.Canvas):
    def __init__(self, parent, size=120, animate=True, shadow=True, bg=None):
        try:
            bg = bg or parent.cget("bg")
        except tk.TclError:
            bg = T.CARD
        self.size, self.with_shadow = size, shadow
        height = int(size * (1.25 if shadow else 1.0))
        super().__init__(parent, width=size, height=height, bg=bg, highlightthickness=0, bd=0)
        self.mode, self.t, self.blink_at, self.offset = "idle", 0.0, 2.5, 0.0
        self._draw()
        self._job = self.after(40, self._tick) if animate else None
        self.bind("<Destroy>", lambda e: self._job and self.after_cancel(self._job))

    # ------------------------------------------------------------ drawing (once; animation moves the items)
    def _draw(self):
        s = self.size
        cx, cy, r = s / 2, s * 0.58, s * 0.36
        if self.with_shadow:
            self.shadow = self.create_oval(cx - r * 0.75, s * 1.08, cx + r * 0.75, s * 1.18, fill=SHADOW, outline="")
        # antenna
        self.create_line(cx, cy - r - s * 0.13, cx, cy - r + 2, fill=TRIM, width=max(2, s * 0.05), tags="bot")
        b = s * 0.075
        self.ball = self.create_oval(cx - b, cy - r - s * 0.13 - b * 1.6, cx + b, cy - r - s * 0.13 + b * 0.4,
                                     fill="#111111", outline="", tags="bot")
        # head: vertical gradient clipped to the circle, then a darker cap at the top
        steps = max(12, int(2 * r))
        for i in range(steps):
            y = cy - r + 2 * r * i / steps
            half = math.sqrt(max(0.0, r * r - (y - cy) ** 2))
            self.create_line(cx - half, y, cx + half, y, fill=_mix(HEAD_TOP, HEAD_BOTTOM, i / steps),
                             width=max(1, 2 * r / steps + 1), tags="bot")
        self.create_arc(cx - r * 0.55, cy - r - r * 0.12, cx + r * 0.55, cy - r + r * 0.5, start=20, extent=140,
                        fill=TRIM, outline="", style="chord", tags="bot")
        # visor (dark, rounded, with a trim)
        vx, vy, vw, vh = cx, cy - r * 0.02, r * 0.86, r * 0.42
        self._capsule(vx - vw - 3, vy - vh - 3, vx + vw + 3, vy + vh + 3, TRIM)
        self._capsule(vx - vw, vy - vh, vx + vw, vy + vh, VISOR)
        # eyes: happy arcs (open) / lines (blink) / dots (thinking)
        e, ew = r * 0.22, max(2, s * 0.045)
        self.eyes_open, self.eyes_shut, self.eyes_dots = [], [], []
        for ex in (vx - vw * 0.45, vx + vw * 0.45):
            ey = vy - vh * 0.05
            self.eyes_open.append(self.create_arc(ex - e, ey - e * 0.9, ex + e, ey + e * 1.1, start=0, extent=180,
                                                  style="arc", outline=EYES, width=ew, tags="bot"))
            self.eyes_shut.append(self.create_line(ex - e, ey + e * 0.1, ex + e, ey + e * 0.1, fill=EYES,
                                                   width=ew, capstyle="round", state="hidden", tags="bot"))
            d = e * 0.32
            self.eyes_dots.append(self.create_oval(ex - d, ey - d, ex + d, ey + d, fill=EYES, outline="",
                                                   state="hidden", tags="bot"))
        # smile
        m = r * 0.11
        self.create_arc(vx - m, vy + vh * 0.25 - m, vx + m, vy + vh * 0.25 + m, start=180, extent=180,
                        fill="white", outline="", style="chord", tags="bot")

    def _capsule(self, x1, y1, x2, y2, color):
        h = y2 - y1
        self.create_oval(x1, y1, x1 + h, y2, fill=color, outline="", tags="bot")
        self.create_oval(x2 - h, y1, x2, y2, fill=color, outline="", tags="bot")
        self.create_rectangle(x1 + h / 2, y1, x2 - h / 2, y2, fill=color, outline="", tags="bot")

    # ------------------------------------------------------------ animation
    def set_mode(self, mode):
        self.mode = mode
        dots = "normal" if mode == "thinking" else "hidden"
        for i in self.eyes_dots:
            self.itemconfigure(i, state=dots)
        for i in self.eyes_open:
            self.itemconfigure(i, state="hidden" if mode == "thinking" else "normal")
        for i in self.eyes_shut:
            self.itemconfigure(i, state="hidden")
        self.itemconfigure(self.ball, fill=T.ORANGE if mode == "thinking" else "#111111")

    def _tick(self):
        self._job = None
        if not self.winfo_exists():
            return
        speed = 0.22 if self.mode == "thinking" else 0.09
        self.t += speed
        amp = self.size * (0.05 if self.mode == "thinking" else 0.035)
        new = math.sin(self.t) * amp
        self.move("bot", 0, new - self.offset)
        self.offset = new
        if self.with_shadow:  # the shadow shrinks when the robot is higher
            s, k = self.size, 1 - (new + amp) / (8 * amp)
            cx, w = s / 2, s * 0.36 * 0.75 * (0.8 + 0.2 * k)
            self.coords(self.shadow, cx - w, s * 1.08, cx + w, s * 1.18)
        if self.mode == "thinking":  # eyes look left and right
            dx = math.sin(self.t * 0.7) * self.size * 0.02 - getattr(self, "_look", 0)
            for i in self.eyes_dots:
                self.move(i, dx, 0)
            self._look = getattr(self, "_look", 0) + dx
        else:  # a blink every few seconds
            self.blink_at -= 0.04
            shut = -0.15 < self.blink_at <= 0
            for i in self.eyes_open:
                self.itemconfigure(i, state="hidden" if shut else "normal")
            for i in self.eyes_shut:
                self.itemconfigure(i, state="normal" if shut else "hidden")
            if self.blink_at <= -0.15:
                self.blink_at = 3.2
        self._job = self.after(40, self._tick)
