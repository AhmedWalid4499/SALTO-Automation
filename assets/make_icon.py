"""Generates assets/app.ico (orange tile with an 'S')."""
import os

from PIL import Image, ImageDraw, ImageFont

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, size - 8, size - 8], radius=48, fill=(255, 121, 0, 255))
try:
    font = ImageFont.truetype("segoeuib.ttf", 170)
except OSError:
    font = ImageFont.load_default()
box = d.textbbox((0, 0), "S", font=font)
d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), "S", font=font, fill="white")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
