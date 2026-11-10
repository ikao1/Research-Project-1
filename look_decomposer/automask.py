#!/usr/bin/env python3
"""Auto masks for compositing: subject, people, tonal ranges, and color ranges.

Writes an 8-bit grayscale PNG the size of the input: white = selected.

Usage:
    python3 -m look_decomposer.automask <image> -o matte.png --mode subject
    python3 -m look_decomposer.automask <image> -o matte.png --mode color --hue 0 --hue-width 35
    python3 -m look_decomposer.automask --build      # compile the Vision helper (macOS)
    python3 -m look_decomposer.automask --status

Modes:
    subject     Apple Vision foreground subject(s). Accurate for objects and people
                in photos and illustrations. Needs macOS 14+ and the helper.
    people      Apple Vision person segmentation. Accurate for photographed people
                only; it missed illustrated characters in testing.
    highlights  bright areas (luma)
    midtones    middle tones (luma)
    shadows     dark areas (luma)
    color       one hue range: --hue (0 red, 60 yellow, 120 green, 180 cyan,
                240 blue, 300 magenta), --hue-width (degrees), --min-sat (0-100)

Post-processing for every mode:
    --grow N     expand the matte by N pixels (negative shrinks it)
    --feather R  soften the edge with a Gaussian blur of radius R pixels
    --invert     select the opposite area
"""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
HELPER_SRC = HERE / "tools" / "automask_vision.swift"
HELPER_BIN = HERE / "bin" / "automask_vision"
SDK_CANDIDATES = [
    "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
    "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk",
    "/Library/Developer/CommandLineTools/SDKs/MacOSX15.sdk",
]
VISION_MODES = ("subject", "people")
LUMA_MODES = {
    # trapezoid in 0..1: (start of ramp, full start, full end, end of ramp)
    "highlights": (0.50, 0.72, 1.00, 1.00),
    "midtones": (0.20, 0.40, 0.60, 0.80),
    "shadows": (0.00, 0.00, 0.25, 0.45),
}
MODES = VISION_MODES + tuple(LUMA_MODES) + ("color",)


def trapezoid(v, a, b, c, d):
    if v <= a or v >= d:
        return 0.0
    if v < b:
        return (v - a) / max(1e-9, b - a)
    if v <= c:
        return 1.0
    return (d - v) / max(1e-9, d - c)


def lut_from(fn):
    return [int(round(255 * max(0.0, min(1.0, fn(i / 255.0))))) for i in range(256)]


def helper_status():
    if not HELPER_BIN.exists():
        return "not built"
    try:
        result = subprocess.run([str(HELPER_BIN)], capture_output=True, text=True)
    except OSError as exc:
        return "cannot run (%s)" % exc
    return "ready" if "usage" in result.stderr else "unexpected output"


def build_helper():
    if platform.system() != "Darwin":
        raise SystemExit("The Vision helper needs macOS.")
    if not HELPER_SRC.exists():
        raise SystemExit("Missing source: %s" % HELPER_SRC)
    HELPER_BIN.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for sdk in SDK_CANDIDATES:
        if not Path(sdk).exists():
            continue
        cmd = ["swiftc", "-O", "-sdk", sdk, str(HELPER_SRC), "-o", str(HELPER_BIN)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and HELPER_BIN.exists():
            print("Built %s (SDK %s)" % (HELPER_BIN, Path(sdk).name))
            return 0
        errors.append("%s: %s" % (Path(sdk).name, (result.stderr or "").strip().splitlines()[:1]))
    print("Could not build the Vision helper.")
    for line in errors:
        print("  " + str(line))
    print("Install the Xcode command line tools (xcode-select --install) and try again.")
    return 1


def run_vision(mode, image_path):
    if not HELPER_BIN.exists():
        raise SystemExit("The Vision helper is not built. Run: "
                         "python3 -m look_decomposer.automask --build")
    tmp = HERE / "bin" / ("_vision_%s.png" % mode)
    result = subprocess.run([str(HELPER_BIN), mode, str(image_path), str(tmp)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise SystemExit(message or "Vision failed (exit %d)" % result.returncode)
    matte = Image.open(tmp).convert("L")
    tmp.unlink()
    return matte


def luma_matte(img, mode):
    luma = img.convert("L")
    a, b, c, d = LUMA_MODES[mode]
    return luma.point(lut_from(lambda v: trapezoid(v, a, b, c, d)))


def hue_distance(h, center):
    d = abs(h - center)
    return min(d, 255 - d)


def color_matte(img, hue_deg, width_deg, min_sat):
    hsv = img.convert("HSV")
    h, s, _ = hsv.split()
    center = (hue_deg % 360) / 360.0 * 255.0
    half = max(1.0, width_deg / 360.0 * 255.0 / 2.0)
    feather = half * 0.5
    hue_lut = []
    for i in range(256):
        dist = hue_distance(i, center)
        if dist <= half:
            hue_lut.append(255)
        elif dist >= half + feather:
            hue_lut.append(0)
        else:
            hue_lut.append(int(round(255 * (1.0 - (dist - half) / feather))))
    sat_floor = min_sat / 100.0 * 255.0
    sat_lut = []
    for i in range(256):
        if i >= sat_floor + 12:
            sat_lut.append(255)
        elif i <= sat_floor:
            sat_lut.append(0)
        else:
            sat_lut.append(int(round(255 * (i - sat_floor) / 12.0)))
    return ImageChops.multiply(h.point(hue_lut), s.point(sat_lut))


def post_process(matte, grow, feather, invert):
    if grow > 0:
        matte = matte.filter(ImageFilter.MaxFilter(2 * grow + 1))
    elif grow < 0:
        matte = matte.filter(ImageFilter.MinFilter(2 * (-grow) + 1))
    if feather > 0:
        matte = matte.filter(ImageFilter.GaussianBlur(feather))
    if invert:
        matte = ImageChops.invert(matte)
    return matte


def make_matte(image_path, mode, hue=0.0, hue_width=35.0, min_sat=20.0,
               grow=0, feather=0.0, invert=False):
    if mode not in MODES:
        raise SystemExit("Unknown mode %r. Choose one of: %s" % (mode, ", ".join(MODES)))
    if mode in VISION_MODES:
        matte = run_vision(mode, image_path)
    else:
        img = Image.open(image_path).convert("RGB")
        if mode == "color":
            matte = color_matte(img, hue, hue_width, min_sat)
        else:
            matte = luma_matte(img, mode)
    return post_process(matte, int(grow), float(feather), bool(invert))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", nargs="?", help="Image to mask")
    parser.add_argument("-o", "--output", help="Matte PNG to write")
    parser.add_argument("--mode", default="subject", choices=MODES)
    parser.add_argument("--hue", type=float, default=0.0)
    parser.add_argument("--hue-width", type=float, default=35.0)
    parser.add_argument("--min-sat", type=float, default=20.0)
    parser.add_argument("--grow", type=int, default=0)
    parser.add_argument("--feather", type=float, default=0.0)
    parser.add_argument("--invert", action="store_true")
    parser.add_argument("--build", action="store_true", help="Compile the Vision helper")
    parser.add_argument("--status", action="store_true", help="Show what is available")
    args = parser.parse_args(argv)

    if args.build:
        return build_helper()
    if args.status:
        print("Platform     : %s %s" % (platform.system(), platform.mac_ver()[0]))
        print("Vision helper: %s (%s)" % (helper_status(), HELPER_BIN))
        print("Modes        : %s" % ", ".join(MODES))
        return 0

    if not args.image or not args.output:
        parser.error("an image and -o OUTPUT are required")
    image = Path(args.image).expanduser().resolve()
    if not image.exists():
        parser.error("Image not found: %s" % image)

    matte = make_matte(image, args.mode, hue=args.hue, hue_width=args.hue_width,
                       min_sat=args.min_sat, grow=args.grow, feather=args.feather,
                       invert=args.invert)
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    matte.save(out)

    histogram = matte.histogram()
    total = sum(histogram)
    selected = sum(histogram[128:])
    print(json.dumps({"matte": str(out), "mode": args.mode,
                      "size": list(matte.size),
                      "selected_fraction": round(selected / max(1, total), 4)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
