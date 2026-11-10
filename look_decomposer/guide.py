#!/usr/bin/env python3
"""Generate a rule-based markdown how-to guide from an analysis JSON.

Each step follows the builder's layer order (LOOK 01 is applied first) and
quotes the analyzer's note for that aspect, so every value comes with its
reason and confidence.

Usage:
    python3 -m look_decomposer.guide <analysis.json> [-o guide.md]
"""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from look_decomposer import validate
else:
    from . import validate

# (aspect key, AE effect shown to the user, layer label, [(field, label)])
# Order matches ORDER in ae/look_fx.jsx.
STEPS = [
    ("exposure", "Exposure", "Exposure",
     [("stops", "Stops"), ("gamma", "Gamma")]),
    ("levels", "Levels (Individual Controls)", "Levels / Contrast",
     [("input_black", "Input black"), ("input_white", "Input white"),
      ("output_black", "Output black"), ("output_white", "Output white")]),
    ("white_balance", "White Balance (Lumetri)", "White Balance",
     [("temperature", "Temperature"), ("tint", "Tint")]),
    ("saturation", "Saturation (Color Balance (HLS))", "Saturation",
     [("amount", "Saturation")]),
    ("split_tone", "Split Tone (Tint)", "Split Tone",
     [("shadows_hex", "Shadows color"), ("highlights_hex", "Highlights color"),
      ("strength", "Strength")]),
    ("blur", "Gaussian Blur", "Blur",
     [("radius_px", "Radius (px)")]),
    ("glow", "Glow", "Glow",
     [("threshold", "Threshold"), ("radius_px", "Radius (px)"),
      ("intensity", "Intensity")]),
    ("vignette", "Vignette (Lumetri)", "Vignette",
     [("amount", "Amount")]),
    ("grain", "Grain (Noise)", "Grain",
     [("amount", "Amount"), ("monochrome", "Monochrome")]),
]


def _format_value(value):
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return ("%.3f" % value).rstrip("0").rstrip(".")
    return str(value)


def _notes_by_topic(analysis):
    out = {}
    for note in analysis.get("notes") or []:
        out.setdefault(note.get("topic"), []).append(note)
    return out


def build_guide(analysis):
    look = analysis.get("look") or {}
    notes = _notes_by_topic(analysis)
    name = analysis.get("name", "look")
    source = (analysis.get("source") or {}).get("path", "unknown")
    overall = analysis.get("overall_confidence")

    lines = []
    lines.append("# How to rebuild `%s` in After Effects" % name)
    lines.append("")
    lines.append("- Source: `%s`" % source)
    if overall is not None:
        lines.append("- Overall confidence: %.2f" % overall)
    lines.append("")
    lines.append("Build the comp with `python3 -m look_decomposer.build <analysis.json>`, "
                 "or apply the effects below by hand in this order. Each step is one "
                 "adjustment layer; drag the matching slider in `LOOK CONTROLS` to adjust it.")
    lines.append("")

    step_no = 0
    skipped = []
    for aspect, effect, label, fields in STEPS:
        section = look.get(aspect)
        if not section or not any(k != "confidence" for k in section):
            skipped.append(label)
            continue
        step_no += 1
        lines.append("## %02d. %s" % (step_no, label))
        lines.append("")
        lines.append("Effect: **%s**" % effect)
        lines.append("")
        for key, field_label in fields:
            if key in section:
                lines.append("- %s: %s" % (field_label, _format_value(section[key])))
        lines.append("")
        for note in notes.get(aspect, []):
            lines.append("> Why: %s" % note.get("message", ""))
            if note.get("confidence") is not None:
                lines.append(">")
                lines.append("> Confidence: %.2f" % note["confidence"])
            lines.append("")

    if skipped:
        lines.append("## Not adjusted")
        lines.append("")
        lines.append("The analyzer found no measurable change for: %s. "
                     "These layers are left neutral." % ", ".join(skipped))
        lines.append("")

    general = notes.get("general", [])
    if general:
        lines.append("## Caveats")
        lines.append("")
        for note in general:
            lines.append("- %s" % note.get("message", ""))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("analysis", help="Analysis JSON file")
    parser.add_argument("-o", "--output", help="Write markdown here "
                        "(default: stdout)")
    args = parser.parse_args(argv)

    path = Path(args.analysis).expanduser().resolve()
    if not path.exists():
        parser.error("Analysis file not found: %s" % path)
    analysis = json.loads(path.read_text(encoding="utf-8"))
    errors = validate.validate(analysis)
    if errors:
        print("Analysis JSON failed validation:", file=sys.stderr)
        for error in errors:
            print("  - %s" % error, file=sys.stderr)
        return 2

    markdown = build_guide(analysis)
    if args.output:
        out = Path(args.output).expanduser()
        out.write_text(markdown, encoding="utf-8")
        print("Wrote %s" % out, file=sys.stderr)
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
