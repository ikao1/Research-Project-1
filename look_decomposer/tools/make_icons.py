#!/usr/bin/env python3
"""Draws the icons shown next to the Look Decomposer sliders.

Writes 24x24 PNG files (light grey on transparent) to look_decomposer/ae_panel/icons/.
Each icon is drawn at 96x96 and shrunk, so edges stay clean.

Usage:
    python3 look_decomposer/tools/make_icons.py
"""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "ae_panel" / "icons"
SS = 96
FINAL = 24
INK = (208, 208, 208, 255)
MID = (120, 120, 120, 255)
DARK = (34, 34, 34, 255)


def sun(d, img):
    c = SS / 2
    d.ellipse((c - 16, c - 16, c + 16, c + 16), fill=INK)
    for k in range(8):
        a = k * math.pi / 4
        d.line((c + 26 * math.cos(a), c + 26 * math.sin(a),
                c + 38 * math.cos(a), c + 38 * math.sin(a)), fill=INK, width=7)


def histogram_marker(d, x):
    base = 72
    for i, hh in enumerate([14, 26, 42, 58, 36, 20]):
        x0 = 14 + i * 11
        d.rectangle((x0, base - hh, x0 + 7, base), fill=INK)
    d.line((10, base, 86, base), fill=INK, width=4)
    d.polygon([(x, 80), (x - 9, 92), (x + 9, 92)], fill=INK)


def black_point(d, img):
    histogram_marker(d, 18)


def white_point(d, img):
    histogram_marker(d, 78)


def faded_blacks(d, img):
    d.rectangle((18, 18, 78, 78), fill=DARK)
    d.rectangle((20, 50, 76, 76), fill=MID)
    d.rectangle((18, 18, 78, 78), outline=INK, width=5)


def thermometer(d, img):
    d.rounded_rectangle((38, 12, 58, 64), radius=10, outline=INK, width=5)
    d.ellipse((28, 56, 68, 92), fill=INK)
    d.rectangle((44, 36, 52, 70), fill=INK)


def drop(d, img):
    d.ellipse((24, 40, 72, 88), fill=INK)
    d.polygon([(48, 10), (26, 54), (70, 54)], fill=INK)


def tint(d, img):
    d.ellipse((24, 40, 72, 88), outline=INK, width=5)
    d.line((48, 10, 24, 58), fill=INK, width=5)
    d.line((48, 10, 72, 58), fill=INK, width=5)
    d.ellipse((40, 58, 56, 74), fill=INK)


def split_tone(d, img):
    d.ellipse((14, 14, 82, 82), outline=INK, width=5)
    d.pieslice((14, 14, 82, 82), 180, 360, fill=INK)
    d.pieslice((14, 14, 82, 82), 0, 180, fill=MID)


def blur(d, img):
    c = SS / 2
    for r, a in [(36, 40), (28, 70), (20, 110), (12, 160), (5, 220)]:
        d.ellipse((c - r, c - r, c + r, c + r), fill=(208, 208, 208, a))


def glow(d, img):
    pts = []
    for k in range(8):
        a = k * math.pi / 4 - math.pi / 2
        r = 42 if k % 2 == 0 else 12
        pts.append((48 + r * math.cos(a), 48 + r * math.sin(a)))
    d.polygon(pts, fill=INK)


def vignette(d, img):
    for y in range(14, 83):
        for x in range(14, 83):
            t = max(abs(x - 48), abs(y - 48)) / 34.0
            v = int(208 * (1 - 0.75 * t * t))
            img.putpixel((x, y), (v, v, v, 255))
    d.rectangle((14, 14, 82, 82), outline=INK, width=5)


def grain(d, img):
    rnd = random.Random(7)
    d.ellipse((12, 12, 84, 84), outline=INK, width=5)
    placed = 0
    while placed < 60:
        x = rnd.uniform(22, 74)
        y = rnd.uniform(22, 74)
        if (x - 48) ** 2 + (y - 48) ** 2 < 26 ** 2:
            r = rnd.choice([2, 3, 4])
            d.ellipse((x - r, y - r, x + r, y + r), fill=INK)
            placed += 1


def contrast(d, img):
    d.ellipse((14, 14, 82, 82), outline=INK, width=5)
    d.pieslice((14, 14, 82, 82), 90, 270, fill=DARK)
    d.pieslice((14, 14, 82, 82), 270, 450, fill=INK)


def highlights(d, img):
    tri = [(10, 80), (48, 18), (86, 80)]
    d.polygon([(48, 18), (64, 44), (32, 44)], fill=INK)
    d.line(tri + [tri[0]], fill=INK, width=5, joint="curve")


def shadows(d, img):
    tri = [(10, 80), (48, 18), (86, 80)]
    d.polygon(tri, fill=MID)
    d.line(tri + [tri[0]], fill=INK, width=5, joint="curve")


def whites(d, img):
    d.rectangle((18, 18, 78, 78), fill=INK)


def blacks(d, img):
    d.rectangle((18, 18, 78, 78), fill=DARK)
    d.rectangle((18, 18, 78, 78), outline=INK, width=5)


def sharpen(d, img):
    d.line([(10, 70), (28, 34), (44, 64), (60, 24), (78, 62), (88, 40)],
           fill=INK, width=6, joint="curve")


def sparkle(d, cx, cy, r):
    k = r * 0.25
    d.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
               (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill=INK)


def vibrance(d, img):
    sparkle(d, 34, 36, 18)
    sparkle(d, 66, 60, 22)
    sparkle(d, 30, 70, 10)


def mix(d, img):
    d.ellipse((12, 28, 60, 76), outline=INK, width=5)
    d.ellipse((36, 28, 84, 76), outline=INK, width=5)


def gauge(d, img):
    d.arc((14, 22, 82, 90), start=180, end=360, fill=INK, width=6)
    d.line((48, 58, 70, 34), fill=INK, width=6)
    d.ellipse((42, 52, 54, 64), fill=INK)


def hue_shift(d, img):
    cx = cy = 48
    r = 30
    d.arc((cx - r, cy - r, cx + r, cy + r), start=30, end=300, fill=INK, width=6)
    a = math.radians(300)
    px, py = cx + r * math.cos(a), cy + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)
    nx, ny = math.cos(a), math.sin(a)
    tip = (px + 12 * tx, py + 12 * ty)
    d.polygon([tip, (px + 9 * nx, py + 9 * ny), (px - 9 * nx, py - 9 * ny)], fill=INK)


def value_half(d, img):
    d.ellipse((16, 16, 80, 80), outline=INK, width=5)
    d.pieslice((16, 16, 80, 80), 0, 180, fill=INK)


def area(d, img):
    d.rectangle((18, 22, 78, 74), outline=INK, width=4)
    for cx, cy in [(18, 22), (78, 22), (18, 74), (78, 74)]:
        d.rectangle((cx - 6, cy - 6, cx + 6, cy + 6), fill=INK)


def dashed_line(d, x1, y1, x2, y2, dash=8, gap=6, width=4):
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    t = 0.0
    while t < length:
        t2 = min(t + dash, length)
        d.line((x1 + ux * t, y1 + uy * t, x1 + ux * t2, y1 + uy * t2), fill=INK, width=width)
        t += dash + gap


def edge_soft(d, img):
    box = [(18, 18), (78, 18), (78, 78), (18, 78), (18, 18)]
    for (x1, y1), (x2, y2) in zip(box, box[1:]):
        dashed_line(d, x1, y1, x2, y2)
    d.rectangle((34, 34, 62, 62), fill=INK)


def move_h(d, img):
    d.line((14, 48, 82, 48), fill=INK, width=5)
    d.polygon([(8, 48), (22, 38), (22, 58)], fill=INK)
    d.polygon([(88, 48), (74, 38), (74, 58)], fill=INK)


def move_v(d, img):
    d.line((48, 14, 48, 82), fill=INK, width=5)
    d.polygon([(48, 8), (38, 22), (58, 22)], fill=INK)
    d.polygon([(48, 88), (38, 74), (58, 74)], fill=INK)


def opacity(d, img):
    d.rectangle((18, 18, 78, 78), outline=INK, width=5)
    cell = 15
    for i in range(4):
        for j in range(4):
            if (i + j) % 2 == 0:
                x0, y0 = 18 + i * cell, 18 + j * cell
                d.rectangle((x0, y0, x0 + cell, y0 + cell), fill=INK)


def blend(d, img):
    d.rectangle((14, 14, 62, 62), outline=INK, width=5)
    d.rectangle((34, 34, 82, 82), outline=INK, width=5)


def grow(d, img):
    box = [(10, 10), (86, 10), (86, 86), (10, 86), (10, 10)]
    for (x1, y1), (x2, y2) in zip(box, box[1:]):
        dashed_line(d, x1, y1, x2, y2)
    d.rectangle((34, 34, 62, 62), fill=INK)


ICONS = {
    "sun": sun, "black_point": black_point, "white_point": white_point,
    "faded_blacks": faded_blacks, "thermometer": thermometer, "drop": drop,
    "tint": tint, "split_tone": split_tone, "blur": blur, "glow": glow,
    "vignette": vignette, "grain": grain, "contrast": contrast,
    "highlights": highlights, "shadows": shadows, "whites": whites,
    "blacks": blacks, "sharpen": sharpen, "vibrance": vibrance, "mix": mix,
    "gauge": gauge, "hue_shift": hue_shift, "value_half": value_half,
    "area": area, "edge_soft": edge_soft, "move_h": move_h, "move_v": move_v,
    "opacity": opacity, "blend": blend, "grow": grow,
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in ICONS.items():
        img = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        fn(d, img)
        img.resize((FINAL, FINAL), Image.LANCZOS).save(OUT / (name + ".png"))
    print("wrote %d icons to %s" % (len(ICONS), OUT))


if __name__ == "__main__":
    main()
