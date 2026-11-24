#!/usr/bin/env python3
"""Resize an image to a small thumbnail PNG (the panel's reference preview).

Usage:
    python3 -m look_decomposer.thumbnail <input> <output>
"""

import sys

from PIL import Image


def main():
    if len(sys.argv) != 3:
        print("usage: python3 -m look_decomposer.thumbnail <input> <output>", file=sys.stderr)
        return 2
    src, out = sys.argv[1], sys.argv[2]
    im = Image.open(src)
    im.thumbnail((240, 240))
    im.convert("RGB").save(out, "PNG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
