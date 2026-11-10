#!/usr/bin/env python3
"""Generate the neutral base plate used by the Look Decomposer test set.

Draws a synthetic scene (sky, sun, mountains, water, rocks) plus calibration
elements (gray ramp, color chart, checkerboard, fine stripes) with PIL only.
Everything is deterministic, so the analyzer has stable reference regions.
"""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 1280, 720
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "test_stills" / "base_plate.png"

SKY_TOP = (95, 150, 210)
SKY_BOTTOM = (215, 220, 228)
SUN_X, SUN_Y = 950, 85


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_sky(img, draw):
    for y in range(360):
        draw.line([(0, y), (W, y)], fill=lerp(SKY_TOP, SKY_BOTTOM, y / 359.0))


def draw_sun(img):
    glow = Image.new("L", (300, 300), 0)
    gd = ImageDraw.Draw(glow)
    for r in range(150, 0, -1):
        falloff = (1.0 - r / 150.0) ** 1.8
        gd.ellipse([150 - r, 150 - r, 150 + r, 150 + r], fill=int(255 * falloff))
    warm = Image.new("RGB", (300, 300), (255, 240, 205))
    img.paste(warm, (SUN_X - 150, SUN_Y - 150), glow)
    d = ImageDraw.Draw(img)
    d.ellipse([SUN_X - 26, SUN_Y - 26, SUN_X + 26, SUN_Y + 26], fill=(255, 252, 238))


def mountain_points(baseline, amp1, period1, amp2, period2, phase):
    points = [(0, baseline)]
    for x in range(0, W + 1, 20):
        y = baseline - amp1 * math.sin(x / period1 + phase) - amp2 * math.sin(x / period2 + phase * 1.7)
        points.append((x, y))
    return points


def draw_mountains(img, draw):
    far = mountain_points(255, 38, 41.0, 14, 11.3, 0.7)
    far.append((W, 400))
    far.append((0, 400))
    draw.polygon(far, fill=(150, 158, 172))

    near = mountain_points(305, 52, 57.0, 18, 17.1, 2.4)
    near.append((W, 420))
    near.append((0, 420))
    draw.polygon(near, fill=(105, 112, 128))


def draw_water(img, draw):
    for y in range(420, H):
        t = (y - 420) / (H - 421)
        draw.line([(0, y), (W, y)], fill=lerp((58, 108, 138), (22, 42, 62), t))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(425, H, 3):
        depth = y - 425
        half = 9 + depth * 0.16
        alpha = max(0, int(95 - depth * 0.22))
        if alpha <= 0:
            continue
        od.line([(SUN_X - half, y), (SUN_X + half, y)], fill=(255, 235, 190, alpha))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))

    rng = random.Random(11)
    sparkle = ImageDraw.Draw(img)
    for _ in range(150):
        x = rng.uniform(680, 1240)
        y = rng.uniform(430, H - 10)
        if abs(x - SUN_X) < 40 and y < 480:
            continue
        bright = rng.randint(150, 220)
        sparkle.point((x, y), fill=(bright, bright + 15, bright + 25))


def draw_foreground(draw):
    draw.polygon([(0, H), (0, 600), (80, 585), (150, 610), (230, 596), (310, 640),
                  (360, H)], fill=(18, 22, 26))
    draw.polygon([(W, H), (W, 640), (1200, 660), (1150, 700), (1120, H)], fill=(24, 28, 32))


def draw_calibration(draw):
    # Gray ramp: 11 steps from black to white
    for i in range(11):
        v = int(round(i * 25.5))
        draw.rectangle([40 + i * 38, 36, 40 + i * 38 + 38, 62], fill=(v, v, v))

    # Mini color chart (6x4)
    chart = [
        (174, 126, 93), (196, 148, 114), (216, 172, 134), (234, 192, 154),
        (170, 60, 60), (120, 40, 40), (200, 140, 50), (230, 190, 60),
        (60, 110, 60), (110, 150, 90), (40, 70, 45), (90, 140, 55),
        (60, 80, 150), (90, 130, 190), (35, 50, 90), (140, 170, 220),
        (140, 60, 120), (190, 120, 170), (70, 140, 150), (120, 180, 190),
        (230, 230, 230), (160, 160, 160), (90, 90, 90), (35, 35, 35),
    ]
    for i, color in enumerate(chart):
        cx = 40 + (i % 6) * 36
        cy = 76 + (i // 6) * 36
        draw.rectangle([cx, cy, cx + 34, cy + 34], fill=color)

    # Checkerboard: high-frequency detail for blur estimation
    for gy in range(6):
        for gx in range(6):
            v = 210 if (gx + gy) % 2 == 0 else 70
            draw.rectangle([400 + gx * 6, 540 + gy * 6,
                           400 + gx * 6 + 6, 540 + gy * 6 + 6], fill=(v, v, v))

    # Fine stripes: second high-frequency pattern
    for i in range(48):
        v = 190 if i % 2 == 0 else 100
        draw.rectangle([400 + i * 3, 584, 400 + i * 3 + 3, 616], fill=(v, v, v))


def main():
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    draw_sky(img, draw)
    draw_sun(img)
    draw_mountains(img, draw)
    draw_water(img, draw)
    draw_foreground(draw)
    draw_calibration(draw)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT, "PNG")
    print("Wrote %s (%dx%d)" % (OUTPUT, W, H))


if __name__ == "__main__":
    main()
