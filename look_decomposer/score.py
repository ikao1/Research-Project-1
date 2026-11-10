#!/usr/bin/env python3
"""Score the analyzer against the ground-truth looks.

For every look in test_stills/looks, analyzes the corresponding render in
test_stills/renders (with the base plate as reference, and standalone) and
compares the predicted parameters against the ground truth.

Usage:
    python3 -m look_decomposer.score [--standalone] [--verbose]
"""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from look_decomposer.analyzer import analyze
else:
    from .analyzer import analyze

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKS_DIR = REPO_ROOT / "test_stills" / "looks"
RENDERS_DIR = REPO_ROOT / "test_stills" / "renders"
PLATE = REPO_ROOT / "test_stills" / "base_plate.png"
SCORES_JSON = REPO_ROOT / "test_stills" / "scores.json"

FIELD_SCALE = {
    ("exposure", "stops"): 1.0,
    ("exposure", "gamma"): 0.5,
    ("white_balance", "temperature"): 100.0,
    ("white_balance", "tint"): 100.0,
    ("saturation", "amount"): 100.0,
    ("levels", "input_black"): 0.25,
    ("levels", "input_white"): 0.25,
    ("levels", "output_black"): 0.25,
    ("levels", "output_white"): 0.25,
    ("split_tone", "strength"): 100.0,
    ("blur", "radius_px"): 4.0,
    ("glow", "intensity"): 1.5,
    ("vignette", "amount"): 3.0,
    ("grain", "amount"): 100.0,
}

# Neutral value for optional numeric fields: a look that omits the section
# is equivalent to these parameter values, not to zero.
NEUTRAL = {
    ("exposure", "gamma"): 1.0,
    ("levels", "input_black"): 0.0,
    ("levels", "input_white"): 1.0,
    ("levels", "output_black"): 0.0,
    ("levels", "output_white"): 1.0,
}

FIELDS = sorted(FIELD_SCALE)


def compare(truth, predicted):
    errors = {}
    for aspect, field in FIELDS:
        t_section = (truth.get("look") or {}).get(aspect) or {}
        p_section = (predicted.get("look") or {}).get(aspect) or {}
        t_value = t_section.get(field)
        p_value = p_section.get(field)
        neutral = NEUTRAL.get((aspect, field), 0.0)
        if t_value is None and p_value is None:
            continue
        t_value = neutral if t_value is None else t_value
        p_value = neutral if p_value is None else p_value
        scale = FIELD_SCALE[(aspect, field)]
        errors["%s.%s" % (aspect, field)] = abs(t_value - p_value) / scale
    if "split_tone" in (truth.get("look") or {}) and "split_tone" in (predicted.get("look") or {}):
        t_rgb = truth["look"]["split_tone"]["shadows_hex"]
        p_rgb = predicted["look"]["split_tone"]["shadows_hex"]
        errors["split_tone.shadows_hex"] = hex_distance(t_rgb, p_rgb)
    return errors


def hex_distance(a, b):
    def rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    ra, rb = rgb(a), rgb(b)
    return sum((x - y) ** 2 for x, y in zip(ra, rb)) ** 0.5 / 441.0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--standalone", action="store_true",
                        help="Analyze without the reference plate")
    parser.add_argument("--verbose", action="store_true",
                        help="Print every field error, not just the summary")
    args = parser.parse_args(argv)

    results = {}
    all_field_errors = {}
    for look_file in sorted(LOOKS_DIR.glob("*.json")):
        truth = json.loads(look_file.read_text(encoding="utf-8"))
        slug = truth["name"]
        render = RENDERS_DIR / ("%s.png" % slug)
        if not render.exists():
            print("missing render for %s" % slug, file=sys.stderr)
            continue
        reference = None if args.standalone else str(PLATE)
        predicted = analyze(str(render), reference, name=slug)
        errors = compare(truth, predicted)
        results[slug] = {
            "mean_error": round(sum(errors.values()) / max(1, len(errors)), 3),
            "fields": {k: round(v, 3) for k, v in errors.items()},
            "predicted": predicted,
        }
        for key, value in errors.items():
            all_field_errors.setdefault(key, []).append(value)

    worst = sorted(((sum(v) / len(v), k) for k, v in all_field_errors.items()),
                   reverse=True)

    print("%-18s %s" % ("look", "mean normalized error"))
    for slug, data in sorted(results.items()):
        print("%-18s %.3f%s" % (slug, data["mean_error"],
                                "" if not args.verbose else ""))
        if args.verbose:
            for key, value in sorted(data["fields"].items()):
                print("    %-28s %.3f" % (key, value))

    print("\n%-28s %s" % ("worst fields (mean error)", ""))
    for mean, key in worst[:12]:
        print("%-28s %.3f" % (key, mean))

    overall = sum(d["mean_error"] for d in results.values()) / max(1, len(results))
    print("\noverall mean error: %.3f (%d looks, %s mode)"
          % (overall, len(results), "standalone" if args.standalone else "reference"))

    SCORES_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("wrote %s" % SCORES_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
