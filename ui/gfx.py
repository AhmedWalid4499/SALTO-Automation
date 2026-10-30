"""Smooth graphics for the UI, drawn with Pillow.

Tk's canvas has no anti-aliasing: a rounded shape drawn with it has jagged edges. Everything rounded is drawn here
at 4x its size and scaled down, then shown as an image. Corners and shadows are made once and stretched to any size
(9-slice), so resizing a window stays fast. Icons come from Windows' own icon font, drawn the same way.
"""
import ctypes
import os
from collections import OrderedDict
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageTk

SS = 4  # supersampling factor
_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
ICON_FONT = next((p for p in (os.path.join(_FONTS, "SegoeIcons.ttf"), os.path.join(_FONTS, "segmdl2.ttf"))
                  if os.path.exists(p)), "")  # Windows 11's Fluent icons; same codes in Windows 10's older font


def rgb(color):
    return ImageColor.getrgb(color)[:3]


def mix(c1, c2, t):
    a, b = rgb(c1), rgb(c2)
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _mask(size, box, r):
    """Anti-aliased coverage of a rounded rectangle. box is (x1, y1, x2, y2) in final pixels (x2, y2 exclusive)."""
    big = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    x1, y1, x2, y2 = (int(round(v * SS)) for v in box)
    ImageDraw.Draw(big).rounded_rectangle((x1, y1, x2 - 1, y2 - 1), max(0, r * SS), fill=255)
    return big.resize(size, Image.Resampling.BOX)


@lru_cache(maxsize=128)
def _tile(r, fill, outline, line, shadow):
    """A small rounded rectangle with room around it for the shadow; rounded() stretches it to any size."""
    c = r + shadow
    size = (2 * c + 2, 2 * c + 2)
    box = (shadow, shadow, size[0] - shadow, size[1] - shadow)
    def layer(color, mask):
        im = Image.new("RGBA", size, rgb(color) + (0,))
        im.putalpha(mask)
        return im

    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if shadow:
        soft = _mask(size, (box[0], box[1] + shadow * 0.4, box[2], box[3] + shadow * 0.4), r)
        soft = soft.filter(ImageFilter.GaussianBlur(shadow / 2.4)).point(lambda v: int(v * 0.09))
        out = Image.alpha_composite(out, layer("#101828", soft))
    out = Image.alpha_composite(out, layer(outline or fill, _mask(size, box, r)))
    if outline:
        inner = _mask(size, (box[0] + line, box[1] + line, box[2] - line, box[3] - line), max(0, r - line))
        out = Image.alpha_composite(out, layer(fill, inner))
    return out


@lru_cache(maxsize=256)
def rounded(w, h, r, fill, outline=None, line=1, shadow=0, bg=None):
    """An RGBA rounded rectangle of exactly w x h pixels (inset by `shadow` on each side for its soft shadow).
    bg: flatten onto this colour (ttk elements cannot show transparency)."""
    r = max(0, min(r, (min(w, h) - 2 * shadow) // 2))
    tile = _tile(r, fill, outline, line, shadow)
    c, n = r + shadow, tile.width
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mw, mh = w - 2 * c, h - 2 * c
    for x, cx in ((0, 0), (w - c, n - c)):
        for y, cy in ((0, 0), (h - c, n - c)):
            out.paste(tile.crop((cx, cy, cx + c, cy + c)), (x, y))
    if mw > 0 and c:
        mid = n // 2
        out.paste(tile.crop((mid, 0, mid + 1, c)).resize((mw, c)), (c, 0))
        out.paste(tile.crop((mid, n - c, mid + 1, n)).resize((mw, c)), (c, h - c))
    if mh > 0 and c:
        mid = n // 2
        out.paste(tile.crop((0, mid, c, mid + 1)).resize((c, mh)), (0, c))
        out.paste(tile.crop((n - c, mid, n, mid + 1)).resize((c, mh)), (w - c, c))
    if mw > 0 and mh > 0:
        out.paste(rgb(fill) + (255,), (c, c, w - c, h - c))
    if bg:
        base = Image.new("RGBA", (w, h), rgb(bg) + (255,))
        base.alpha_composite(out)
        return base
    return out


@lru_cache(maxsize=64)
def gradient(w, h, r, c1, c2):
    """A rounded rectangle with a diagonal colour gradient and a soft light circle in its corner."""
    small = Image.linear_gradient("L").rotate(90).resize((w + h, 1))
    ramp = Image.composite(Image.new("RGB", (w + h, 1), rgb(c2)), Image.new("RGB", (w + h, 1), rgb(c1)), small)
    out = Image.new("RGB", (w, h))
    for y in range(h):
        out.paste(ramp.crop((y, 0, y + w, 1)), (0, y))
    glow = Image.new("L", (w * SS, h * SS), 0)
    d = int(h * 1.5) * SS
    ImageDraw.Draw(glow).ellipse((w * SS - d * 2 // 3, -d // 2, w * SS + d // 3, d // 2), fill=26)
    out.paste((255, 255, 255), (0, 0), glow.resize((w, h), Image.Resampling.BOX))
    out = out.convert("RGBA")
    out.putalpha(_mask((w, h), (0, 0, w, h), r))
    return out


@lru_cache(maxsize=64)
def bar(w, h, r, fill):
    """A chart bar: rounded at the top, flat at the bottom."""
    mask = _mask((w, h + r), (0, 0, w, h + r), r).crop((0, 0, w, h))
    out = Image.new("RGBA", (w, h), rgb(fill) + (255,))
    out.putalpha(mask)
    return out


@lru_cache(maxsize=64)
def dot(d, color, ring=None, line=2):
    """A filled circle; with ring: a circle of that colour, its middle filled with color."""
    big = Image.new("RGBA", (d * SS, d * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    draw.ellipse((0, 0, d * SS - 1, d * SS - 1), fill=rgb(ring or color) + (255,))
    if ring:
        draw.ellipse((line * SS, line * SS, (d - line) * SS - 1, (d - line) * SS - 1), fill=rgb(color) + (255,))
    return big.resize((d, d), Image.Resampling.BOX)


@lru_cache(maxsize=512)
def icon_image(glyph, px, color):
    """An icon from Windows' icon font, px square, in a colour."""
    out = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    if not ICON_FONT or not glyph:
        return out
    font = ImageFont.truetype(ICON_FONT, px * SS)
    big = Image.new("L", (px * SS, px * SS), 0)
    draw = ImageDraw.Draw(big)
    x1, y1, x2, y2 = draw.textbbox((0, 0), glyph, font=font)
    draw.text(((px * SS - (x2 - x1)) // 2 - x1, (px * SS - (y2 - y1)) // 2 - y1), glyph, font=font, fill=255)
    out.paste(rgb(color) + (255,), (0, 0), big.resize((px, px), Image.Resampling.BOX))
    return out


# ---------------------------------------------------------------- for Tk
_photos = OrderedDict()


def tk_image(pil_image, key=None):
    """A Tk image of a Pillow image. Keep a reference to it in the widget that shows it. key: reuse the same one."""
    if key is None:
        return ImageTk.PhotoImage(pil_image)
    if key in _photos:
        _photos.move_to_end(key)
        return _photos[key]
    _photos[key] = img = ImageTk.PhotoImage(pil_image)
    while len(_photos) > 600:
        _photos.popitem(last=False)
    return img


def photo(w, h, r, fill, outline=None, line=1, shadow=0, bg=None):
    return tk_image(rounded(w, h, r, fill, outline, line, shadow, bg), ("r", w, h, r, fill, outline, line, shadow, bg))


def icon(glyph, px, color):
    return tk_image(icon_image(glyph, px, color), ("i", glyph, px, color))


def corners(r, fill):
    """The four corners of a rounded rectangle (top-left, top-right, bottom-left, bottom-right) as Tk images."""
    t = rounded(2 * r, 2 * r, r, fill)
    return [tk_image(t.crop(box), ("c", r, fill, i)) for i, box in enumerate(
        ((0, 0, r, r), (r, 0, 2 * r, r), (0, r, r, 2 * r), (r, r, 2 * r, 2 * r)))]


# ---------------------------------------------------------------- window frame (Windows 11; ignored elsewhere)
def _colorref(color):
    r, g, b = rgb(color)
    return r | g << 8 | b << 16


def window_frame(win, caption=None, text=None, dark=False):
    """Title bar in our colours and rounded window corners, through Windows' desktop window manager."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        def put(attr, value):
            v = ctypes.c_int(value)
            dwm(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
        put(20, int(dark))  # immersive dark mode: light minimise / close buttons
        put(33, 2)          # rounded corners
        if caption:
            put(35, _colorref(caption))
        if text:
            put(36, _colorref(text))
    except Exception:
        pass
