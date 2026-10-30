"""The Friendly SALTO Bot's look and movement: the bot animation kit made for the GOLD app, adapted to SALTO Buddy.

Bot: the floating bot with a breathing glow. AIBanner: the flowing violet > cyan > pink header with the bot, its name,
what it does, the order in view and New chat. ThinkingDots: a wave running through three dots.

The three ideas that make it smooth:
  1. Follow the clock, not a counter. Each tick asks "how many seconds in are we?" and picks the matching
     position, so a busy moment skips a frame instead of slowing the animation.
  2. Prepare pictures once, then only swap or move them. Showing one is very cheap; drawing one is not.
  3. Move by fractions of a pixel. A slow float in whole pixels looks like stairs.
"""
import math
import os
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk

from . import gfx
from . import theme as T

# The colours. A is the violet, B is the cyan. PINK is the third colour of the banner.
THEMES = {"light": {"A": "#7C5CFF", "B": "#1FB6E8"},
          "dark": {"A": "#8B6CFF", "B": "#22C3EE"},
          "futuristic": {"A": "#9D6BFF", "B": "#22D3EE"}}
COLOURS = THEMES["light"]  # our chat is on white
PINK = "#E879F9"
TICK_MS = 15  # how often the clock is checked: about 60 times a second
PICTURE = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "assets", "bot.png")
if not os.path.exists(PICTURE):
    PICTURE = None  # the stand-in robot below


def to_rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """The colour between a and b (t from 0 to 1), as #rrggbb."""
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(to_rgb(a), to_rgb(b)))


def gradient(w, h, c0, c1):
    """A left-to-right gradient picture."""
    line = Image.new("RGBA", (max(w, 2), 1))
    a, b = to_rgb(c0), to_rgb(c1)
    for i in range(line.width):
        t = i / (line.width - 1)
        line.putpixel((i, 0), tuple(round(x + (y - x) * t) for x, y in zip(a, b)) + (255,))
    return line.resize((max(w, 2), max(h, 2)))


def rounded_mask(w, h, r, scale=3):
    """A soft-edged rounded rectangle, drawn big and shrunk so the corners are not jagged."""
    big = Image.new("L", (w * scale, h * scale), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), r * scale, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def stand_in_robot(size=350):
    """Used when there is no picture: a plain robot face."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size / 100
    d.rounded_rectangle((15 * s, 25 * s, 85 * s, 85 * s), 18 * s, fill="#F4F5FF")
    d.line((50 * s, 25 * s, 50 * s, 10 * s), fill="#9D6BFF", width=int(4 * s))
    d.ellipse((44 * s, 4 * s, 56 * s, 16 * s), fill="#22D3EE")
    for x in (35, 65):
        d.ellipse(((x - 7) * s, 45 * s, (x + 7) * s, 59 * s), fill="#2B2D55")
    d.arc((38 * s, 55 * s, 62 * s, 75 * s), 20, 160, fill="#2B2D55", width=int(3 * s))
    return im


def _bot_image(px):
    bot = Image.open(PICTURE).convert("RGBA") if PICTURE else stand_in_robot()
    bot.thumbnail((px, px), Image.LANCZOS)
    return bot


def still(px):
    """The bot as a still Tk picture (the avatar next to an answer)."""
    return gfx.tk_image(_bot_image(px), ("bot", px))


class Bot(tk.Canvas):
    """The floating bot with a breathing glow. Modes: idle (floats), busy (bobs and wiggles), hop (one jump)."""

    SECONDS = {"idle": 2.2, "busy": 0.8, "hop": 0.5}  # how long one loop takes: change these for speed
    FRAMES = {"idle": 66, "busy": 24, "hop": 15}  # about 30 pictures a second
    _kept = {}  # finished pictures, shared by every bot of the same kind

    def __init__(self, parent, size=130, bg=T.CARD, halo=True, mode="idle", clickable=True, colours=COLOURS):
        w, h = size, int(size * 1.22)
        super().__init__(parent, width=w, height=h, background=bg, highlightthickness=0, borderwidth=0)
        self.box, self.halo, self.colours = (size, w, h), halo, colours
        self.mode, self._job, self._begun, self._shown = mode, None, time.perf_counter(), None
        self._item = self.create_image(w // 2, 0, anchor="n")
        if clickable:
            self.configure(cursor="hand2")
            self.bind("<Button-1>", lambda e: self.hop())
        self.bind("<Destroy>", self._stop)
        self.start(mode)

    def _stop(self, _e=None):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _pictures(self, mode):
        """Built the first time a movement is needed, then kept: the slow part happens only once."""
        size, w, h = self.box
        key = (size, mode, self.halo, tuple(self.colours.values()))
        if key in self._kept:
            return self._kept[key]
        bot = _bot_image(int(size * 0.92))
        out = []
        n = self.FRAMES[mode]
        for i in range(n):
            t = i / n  # 0 to 1 around the loop: sine waves make the start and end meet exactly
            if mode == "hop":
                lift, angle = math.sin(math.pi * t) * 0.16, math.sin(2 * math.pi * t) * 6
            else:
                lift = (math.sin(2 * math.pi * t) + 1) / 2 * (0.06 if mode == "idle" else 0.09)
                angle = math.sin(4 * math.pi * t) * 4 if mode == "busy" else 0
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            if self.halo:
                # Two blurred circles, violet and cyan, breathing. Drawn at a quarter of the size and
                # enlarged: a soft glow looks the same and takes a fraction of the time.
                pulse = (math.sin(2 * math.pi * t) + 1) / 2
                small = 4
                g = Image.new("RGBA", (max(1, w // small), max(1, h // small)), (0, 0, 0, 0))
                d = ImageDraw.Draw(g)
                cx, cy, r = g.width / 2, g.height * 0.43, size * (0.27 + 0.03 * pulse) / small
                d.ellipse((cx - r, cy - r, cx + r, cy + r),
                          fill=to_rgb(self.colours["A"]) + (int(120 + 60 * pulse),))
                d.ellipse((cx - r * 0.55, cy - r * 0.9, cx + r * 1.05, cy + r * 0.5),
                          fill=to_rgb(self.colours["B"]) + (int(90 + 50 * pulse),))
                im.alpha_composite(g.filter(ImageFilter.GaussianBlur(size * 0.08 / small)).resize((w, h), Image.BILINEAR))
            # The shadow on the ground: smaller and fainter as the bot rises
            sw, sy = w * (0.62 - lift * 1.4), h * 0.93
            shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).ellipse((w / 2 - sw / 2, sy - h * 0.035, w / 2 + sw / 2, sy + h * 0.035),
                                           fill=(0, 0, 0, max(int(70 - lift * 200), 20)))
            im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(1, size // 40))))
            b = bot.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else bot
            top = max(0.0, h * 0.02 + (0.12 - lift) * size * 0.9)
            whole = int(top)  # the leftover part of a pixel is done by resampling: this stops the "stairs"
            b = b.transform(b.size, Image.AFFINE, (1, 0, 0, 0, 1, whole - top), resample=Image.BICUBIC)
            im.alpha_composite(b, ((w - b.width) // 2, whole))
            out.append(ImageTk.PhotoImage(im))
        self._kept[key] = out
        return out

    def start(self, mode="idle"):
        self.mode, self._begun = mode, time.perf_counter()
        if self._job is None:
            self._tick()

    def hop(self):
        if self.mode != "busy":
            self.start("hop")

    def _tick(self):
        self._job = None
        if not self.winfo_exists():
            return
        if not self.winfo_viewable():  # hidden: look again in a moment, using no power
            self._job = self.after(400, self._tick)
            return
        now = time.perf_counter() - self._begun
        if self.mode == "hop" and now >= self.SECONDS["hop"]:
            self.mode, self._begun, now = "idle", time.perf_counter(), 0.0
        pictures = self._pictures(self.mode)
        picture = pictures[int(now / self.SECONDS[self.mode] * len(pictures)) % len(pictures)]
        if picture is not self._shown:
            self._shown = picture
            self.itemconfigure(self._item, image=picture)
        self._job = self.after(TICK_MS, self._tick)


class AIBanner(tk.Canvas):
    """The bot's header: a flowing violet > cyan > pink gradient with the bot, its name, an "AI" badge, a hint, a chip
    (the order in view) and a New chat button drawn on it. The gradient is ONE long picture sliding under rounded
    corners, not many pictures. The picture repeats exactly, so the moment it restarts cannot be seen."""

    SECONDS = 9  # one loop of the colours

    def __init__(self, parent, title="", hint="", on_new=None, bg=T.CARD, height=64, colours=COLOURS, radius=14):
        self.k = max(1.0, parent.winfo_fpixels("1i") / 96)
        super().__init__(parent, height=height, background=bg, highlightthickness=0, borderwidth=0)
        self.title, self.hint, self.chip, self.on_new = title, hint, "", on_new
        self.corner, self.colours, self.radius = bg, colours, int(radius * self.k)
        self._strip = self._corners = self._bg = self._job = self._later = None
        self._loop, self._size, self._begun, self._over = 0, None, time.perf_counter(), False
        self._f_title, self._f_small = tkfont.Font(font=T.F_SECTION), tkfont.Font(font=T.F_SMALL)
        self._f_button = tkfont.Font(font=T.F_SMALL_BOLD)
        self.bind("<Configure>", self._resized)
        self.bind("<Destroy>", self._stop)

    def _stop(self, _e=None):
        for job in (self._job, self._later):
            if job is not None:
                self.after_cancel(job)
        self._job = self._later = None

    def set(self, hint=None, chip=None):
        if hint is not None:
            self.hint = hint
        if chip is not None:
            self.chip = chip
        if self._size:
            self._overlay(*self._size)

    def _resized(self, e):
        if (e.width, e.height) == self._size or e.width <= 1:
            return
        self._size = (e.width, e.height)
        if self._strip is None:
            self._draw(e.width, e.height)
            return
        # while a window is being dragged larger or smaller: only once it has stopped
        if self._later is not None:
            self.after_cancel(self._later)
        self._later = self.after(140, lambda: self._draw(*self._size))

    def _draw(self, w, h):
        self._later = None
        a, b = self.colours["A"], self.colours["B"]
        stops = [a, b, PINK, a]  # starts and ends on the same colour
        seg = (w * 2) // 3
        loop = seg * 3
        strip = Image.new("RGBA", (loop, h))
        for k in range(3):
            strip.paste(gradient(seg + 1, h, stops[k], stops[k + 1]), (k * seg, 0))
        # Soft white light. Drawn across three loops and cut from the middle, so it wraps around the seam.
        small = 4  # a soft glow can be drawn small and enlarged: much faster, it looks the same
        sw, sh = loop * 3 // small, max(2, h // small)
        glow = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(glow)
        for shift in (0, sw // 3, 2 * sw // 3):
            for cx, cy, r, alpha in ((0.15, 0.2, 0.35, 70), (0.55, 0.9, 0.4, 60), (0.85, 0.1, 0.3, 70)):
                x = shift + cx * sw / 3
                d.ellipse((x - r * sh * 3, cy * sh - r * sh * 3, x + r * sh * 3, cy * sh + r * sh * 3),
                          fill=(255, 255, 255, alpha))
        glow = glow.filter(ImageFilter.GaussianBlur(sh * 0.6)).resize((loop * 3, h), Image.BILINEAR)
        strip.alpha_composite(glow.crop((loop, 0, loop * 2, h)))
        # One banner's width of the start is added at the end, so the view never runs off the picture
        wide = Image.new("RGBA", (loop + w, h))
        wide.paste(strip, (0, 0))
        wide.paste(strip.crop((0, 0, w, h)), (loop, 0))
        self._loop, self._strip = loop, ImageTk.PhotoImage(wide)
        # The rounded corners: a frame in the background colour, lying over the sliding picture
        corners = Image.new("RGBA", (w, h), to_rgb(self.corner) + (255,))
        corners.putalpha(ImageOps.invert(rounded_mask(w, h, self.radius)))
        self._corners = ImageTk.PhotoImage(corners)
        self.delete("all")
        self._bg = self.create_image(0, 0, anchor="nw", image=self._strip)
        self.create_image(0, 0, anchor="nw", image=self._corners)
        self._overlay(w, h)
        if self._job is None:
            self._tick()

    def _glass(self, w, h, alpha):
        """A rounded white pill that lets the colours show through."""
        im = gfx.rounded(w, h, h // 2, "#FFFFFF").copy()
        im.putalpha(im.getchannel("A").point(lambda v: v * alpha // 255))
        return gfx.tk_image(im, ("glass", w, h, alpha))

    def _fit(self, text, font, room):
        while text and font.measure(text) > room:
            text = text[:-2].rstrip()
        return text

    def _overlay(self, w, h):
        """Everything on the gradient. The pictures only move underneath it."""
        self.delete("over")
        k, self._imgs = self.k, []
        x = int(12 * k)
        d = h - int(12 * k)
        self._imgs.append(still(d))
        self.create_image(x, h // 2, image=self._imgs[-1], anchor="w", tags="over")
        x += d + int(10 * k)
        right = w - int(12 * k)
        if self.on_new:
            tw = self._f_button.measure("New chat") + int(40 * k)
            bh = int(30 * k)
            self._imgs.append(self._glass(tw, bh, 255 if self._over else 225))
            self.create_image(right, h // 2, image=self._imgs[-1], anchor="e", tags=("over", "new"))
            self._imgs.append(gfx.icon("", int(13 * k), self.colours["A"]))
            self.create_image(right - tw + int(13 * k), h // 2, image=self._imgs[-1], anchor="w", tags=("over", "new"))
            self.create_text(right - int(13 * k), h // 2, text="New chat", anchor="e", font=T.F_SMALL_BOLD,
                             fill=self.colours["A"], tags=("over", "new"))
            right -= tw + int(8 * k)
            self.tag_bind("new", "<Button-1>", lambda e: self.on_new())
            self.tag_bind("new", "<Enter>", lambda e: self._hover(True))
            self.tag_bind("new", "<Leave>", lambda e: self._hover(False))
        if self.chip:
            tw, bh = self._f_small.measure(self.chip) + int(22 * k), int(24 * k)
            if right - tw > x + int(240 * k):  # never at the cost of the name
                self._imgs.append(self._glass(tw, bh, 60))
                self.create_image(right, h // 2, image=self._imgs[-1], anchor="e", tags="over")
                self.create_text(right - tw // 2, h // 2, text=self.chip, font=T.F_SMALL, fill="white", tags="over")
                right -= tw + int(8 * k)
        y1, y2 = h // 2 - int(11 * k), h // 2 + int(11 * k)
        self.create_text(x, y1, text=self.title, anchor="w", fill="white", font=T.F_SECTION, tags="over")
        bx = x + self._f_title.measure(self.title) + int(8 * k)
        bw, bh = int(26 * k), int(17 * k)
        self._imgs.append(self._glass(bw, bh, 70))
        self.create_image(bx, y1, image=self._imgs[-1], anchor="w", tags="over")
        self.create_text(bx + bw // 2, y1, text="AI", fill="white", font=T.F_CAPS, tags="over")
        hint = self._fit(self.hint, self._f_small, right - x - int(6 * k))
        self.create_text(x, y2, text=hint + ("…" if hint != self.hint else ""), anchor="w", fill="white",
                         font=T.F_SMALL, tags="over")

    def _hover(self, on):
        self._over = on
        self.configure(cursor="hand2" if on else "")
        self._overlay(*self._size)

    def _tick(self):
        self._job = None
        if not self.winfo_exists():
            return
        if not self.winfo_viewable():  # another page is on screen
            self._job = self.after(600, self._tick)
            return
        progress = (time.perf_counter() - self._begun) / self.SECONDS % 1
        self.coords(self._bg, -round(progress * self._loop), 0)
        self._job = self.after(TICK_MS, self._tick)


class ThinkingDots(tk.Canvas):
    """Three dots with a wave running through them: each one is the same sine wave, a little later."""

    SECONDS = 0.9  # one wave

    def __init__(self, parent, bg=T.CARD, text="Thinking...", fg=T.MUTED, colours=COLOURS):
        self.k = k = max(1.0, parent.winfo_fpixels("1i") / 96)
        self.h = int(28 * k)
        super().__init__(parent, width=int(440 * k), height=self.h, background=bg, highlightthickness=0, borderwidth=0)
        self._begun, self._dots, self._job = time.perf_counter(), [], None
        a, b = colours["A"], colours["B"]
        for colour in (a, mix(a, b, 0.5), b):
            self._dots.append(self.create_oval(0, 0, 0, 0, fill=colour, outline=""))
        self._text = self.create_text(int(48 * k), self.h // 2, text=text, anchor="w", fill=fg,
                                      font=(T.FONT, 9, "italic"))
        self.bind("<Destroy>", self._stop)
        self._tick()

    def _stop(self, _e=None):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def set_text(self, text):
        self.itemconfigure(self._text, text=text)

    def _tick(self):
        self._job = None
        if not self.winfo_exists():
            return
        k = self.k
        phase = 2 * math.pi * (time.perf_counter() - self._begun) / self.SECONDS
        for i, dot in enumerate(self._dots):
            p = (math.sin(phase - i * 0.9) + 1) / 2  # 0 to 1; i * 0.9 makes each dot follow the one before
            r = (2.5 + 2.5 * p) * k
            cx, cy = (10 + i * 13) * k, self.h / 2 - 3 * p * k
            self.coords(dot, cx - r, cy - r, cx + r, cy + r)
        self._job = self.after(TICK_MS, self._tick)
