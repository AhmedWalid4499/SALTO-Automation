"""Generates the SALTO Buddy logo: assets/app.ico (window, taskbar, installer) and logo_*.png (sidebar).

An orange tile (soft top-to-bottom gradient) with a white chat bubble - Buddy, the assistant - holding an
orange "S" for SALTO. Drawn at 4x and scaled down so the edges stay smooth at 16 px.
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TOP, BOTTOM = (255, 140, 26), (240, 98, 0)   # Orange #FF7900 family
WHITE = (255, 255, 255, 255)


def logo(size):
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # tile with a vertical gradient
    grad = Image.new("RGBA", (1, s))
    for y in range(s):
        t = y / (s - 1)
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,))
    grad = grad.resize((s, s))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.24), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # chat bubble: rounded body + a tail at the bottom left
    l, t, r, b = s * 0.19, s * 0.20, s * 0.81, s * 0.70
    d.rounded_rectangle([l, t, r, b], radius=int(s * 0.16), fill=WHITE)
    d.polygon([(l + s * 0.10, b - s * 0.04), (l + s * 0.05, s * 0.84), (l + s * 0.28, b - s * 0.02)], fill=WHITE)
    # the S
    try:
        font = ImageFont.truetype("segoeuib.ttf", int(s * 0.42))
    except OSError:
        font = ImageFont.load_default()
    box = d.textbbox((0, 0), "S", font=font)
    cx, cy = (l + r) / 2, (t + b) / 2
    d.text((cx - (box[2] - box[0]) / 2 - box[0], cy - (box[3] - box[1]) / 2 - box[1]), "S", font=font,
           fill=BOTTOM + (255,))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    big = logo(256)
    big.save(os.path.join(HERE, "app.ico"), sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
                                                   (64, 64), (128, 128), (256, 256)])
    for px in (32, 40, 48, 64, 80, 96):
        logo(px).save(os.path.join(HERE, f"logo_{px}.png"))
    big.save(os.path.join(HERE, "logo_256.png"))
    print("written to", HERE)
