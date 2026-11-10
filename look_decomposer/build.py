#!/usr/bin/env python3
"""Build an editable After Effects comp from a look-decomposer analysis JSON.

Usage:
    python3 -m look_decomposer.build <analysis.json> [options]

Options:
    --source PATH     Override the source media path
    --mode MODE       edit (default: adjustment layers + sliders) or flat
    --prefix NAME     Comp-name prefix (default LOOK, or GEN for flat)
    --no-controls     Skip the LOOK CONTROLS slider null (edit mode only)
    --export PNG      Also export frame 0 of the built comp to this PNG
    --no-open         Do not bring the comp up in a viewer

Example:
    python3 -m look_decomposer.build test_stills/looks/noir.json --export out.png
"""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from look_decomposer import ae_transport, validate
else:
    from . import ae_transport, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("analysis", help="Path to an analysis JSON file")
    parser.add_argument("--source", help="Override source media path")
    parser.add_argument("--mode", choices=("edit", "flat"), default="edit")
    parser.add_argument("--prefix", help="Comp-name prefix (default LOOK, GEN for flat)")
    parser.add_argument("--no-controls", action="store_true",
                        help="Skip the LOOK CONTROLS slider null (edit mode)")
    parser.add_argument("--export", help="Export frame 0 of the built comp to this PNG")
    parser.add_argument("--no-open", action="store_true", help="Do not open the comp viewer")
    args = parser.parse_args(argv)

    analysis_path = Path(args.analysis).expanduser().resolve()
    if not analysis_path.exists():
        parser.error("Analysis file not found: %s" % analysis_path)

    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    errors = validate.validate(analysis)
    if errors:
        print("Analysis JSON failed validation:", file=sys.stderr)
        for error in errors:
            print("  - %s" % error, file=sys.stderr)
        return 2

    source = args.source
    if not source:
        source = (analysis.get("source") or {}).get("path")
        if source:
            candidate = Path(source).expanduser()
            if not candidate.is_absolute():
                candidate = analysis_path.parent / candidate
            source = str(candidate.resolve())
    if not source:
        parser.error("No source path (use --source or set analysis.source.path)")

    options = {"mode": args.mode, "open": not args.no_open}
    if args.prefix:
        options["prefix"] = args.prefix
    elif args.mode == "flat":
        options["prefix"] = "GEN"
    if args.no_controls:
        options["controls"] = False
    if args.export:
        options["export_png"] = str(Path(args.export).expanduser().resolve())

    response = ae_transport.build_comp(analysis, source, options)
    if not response.get("ok"):
        print("AE script error:\n%s" % response.get("error"), file=sys.stderr)
        return 1

    result = response.get("result") or {}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    warnings = result.get("warnings") or []
    if warnings:
        print("\n%d warning(s) while building:" % len(warnings), file=sys.stderr)
        for warning in warnings:
            print("  - %s" % warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
