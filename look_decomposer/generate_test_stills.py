#!/usr/bin/env python3
"""Render the ground-truth test stills in After Effects.

For every look JSON in test_stills/looks/, this builds a "flat" comp from the
base plate (the exact effect stack of the analysis, applied directly), exports
frame 0 as a PNG next to the JSON, and finally saves the AE project so the
ground truth stays inspectable.

Each look JSON is its own ground truth: the pair (renders/<slug>.png,
looks/<slug>.json) is what the Nov-17 analyzer will be scored against.

Usage:
    python3 -m look_decomposer.generate_test_stills [--regenerate-plate]
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

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKS_DIR = REPO_ROOT / "test_stills" / "looks"
RENDERS_DIR = REPO_ROOT / "test_stills" / "renders"
BASE_PLATE = REPO_ROOT / "test_stills" / "base_plate.png"
GROUND_TRUTH_AEP = REPO_ROOT / "test_stills" / "ground_truth.aep"


def save_project(path, timeout=120):
    code = (
        'var p = app.project;\n'
        'if (!p) { throw new Error("No project open"); }\n'
        'var f = new File(%s);\n'
        'var folder = f.parent; if (!folder.exists) { folder.create(); }\n'
        'p.save(f);\n'
        'return { path: p.file.fsName };\n'
    ) % json.dumps(str(path))
    return ae_transport.run_jsx(code, timeout=timeout)


def remove_stale_gen_comps(slugs, timeout=60):
    code = (
        'var p = app.project;\n'
        'if (!p) { return { removed: 0 }; }\n'
        'var wanted = %s;\n'
        'var removed = 0;\n'
        'for (var i = p.numItems; i >= 1; i--) {\n'
        '    var it = p.item(i);\n'
        '    if (it instanceof CompItem && it.name.indexOf("GEN — ") === 0) {\n'
        '        it.remove(); removed++;\n'
        '    }\n'
        '}\n'
        'return { removed: removed };\n'
    ) % json.dumps(slugs)
    return ae_transport.run_jsx(code, timeout=timeout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--regenerate-plate", action="store_true",
                        help="Re-render base_plate.png even if it exists")
    args = parser.parse_args(argv)

    if args.regenerate_plate or not BASE_PLATE.exists():
        from look_decomposer import make_base_plate
        make_base_plate.main()
    elif not BASE_PLATE.exists():
        parser.error("Base plate missing: %s" % BASE_PLATE)

    look_files = sorted(LOOKS_DIR.glob("*.json"))
    if not look_files:
        parser.error("No look JSONs found in %s" % LOOKS_DIR)

    slugs = [json.loads(f.read_text(encoding="utf-8"))["name"] for f in look_files]
    cleanup = remove_stale_gen_comps(slugs)
    if cleanup.get("ok") and (cleanup.get("result") or {}).get("removed"):
        print("Removed %d stale GEN comps" % cleanup["result"]["removed"])

    failures = 0
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    for look_file in look_files:
        analysis = json.loads(look_file.read_text(encoding="utf-8"))
        errors = validate.validate(analysis)
        if errors:
            print("SKIP %s (invalid):" % look_file.name)
            for error in errors:
                print("  - %s" % error)
            failures += 1
            continue

        slug = analysis["name"]
        png_path = RENDERS_DIR / ("%s.png" % slug)
        options = {
            "mode": "flat",
            "prefix": "GEN",
            "open": False,
            "export_png": str(png_path),
        }
        try:
            response = ae_transport.build_comp(analysis, str(BASE_PLATE), options)
        except Exception as exc:  # BridgeError or similar
            print("FAIL %s: %s" % (look_file.name, exc))
            failures += 1
            continue

        if not response.get("ok"):
            print("FAIL %s:\n%s" % (look_file.name, response.get("error")))
            failures += 1
            continue

        result = response.get("result") or {}
        warnings = result.get("warnings") or []
        status = "ok" if result.get("exported_png") else "no-png"
        print("%s  %-18s layers=%d  %s" % (
            status, slug, len(result.get("layers") or []), png_path.name))
        for warning in warnings:
            print("    warning: %s" % warning)

    save = save_project(GROUND_TRUTH_AEP)
    if save.get("ok"):
        print("Saved AE project: %s" % (save.get("result") or {}).get("path"))
    else:
        print("Could not save AE project:\n%s" % save.get("error"), file=sys.stderr)
        failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
