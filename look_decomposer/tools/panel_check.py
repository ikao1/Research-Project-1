#!/usr/bin/env python3
"""Reload the Look Decomposer panel in the open After Effects and check it.

Checks, without changing the project (no comps, footage, or layers are created):
  - the panel loads and reports the version in ae_panel/LookDecomposer.jsx
  - four tabs, 12 look sliders, 10 grade sliders, and an icon on every slider row
  - the scroll bar on every tab: no control sticks out of the viewport, the view
    is never blank, and every control can be reached

Needs After Effects open with the panel installed (python3 -m look_decomposer.install_panel).
Opens a floating window and closes it again.

Usage:
    python3 look_decomposer/tools/panel_check.py              # newest installed AE version
    python3 look_decomposer/tools/panel_check.py --ae 26.5

Exit codes: 0 all checks pass, 1 a check failed, 2 After Effects or the panel not available.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from look_decomposer import ae_transport, install_panel  # noqa: E402

PANEL_SRC = REPO / "look_decomposer" / "ae_panel" / "LookDecomposer.jsx"
EXPECTED_PARTS = 12
EXPECTED_GRADE = 10
EXPECTED_TABS = 4

JSX_TEMPLATE = r"""
var LOADER = __LOADER__;
var lines = [];
/* A docked panel may be the handle in $.global: never close it, and put it back. */
var prev = $.global.LookDecomposer;
var prevIsDocked = false;
try { prevIsDocked = !!(prev && prev.ui && prev.ui.win instanceof Panel); } catch (e00) { }
if (!prevIsDocked) {
    try {
        if (prev && prev.ui && prev.ui.win) { prev.ui.win.close(); }
    } catch (e0) { }
}
$.global.LookDecomposer = null;
try {
    $.evalFile(new File(LOADER));
} catch (e) {
    return "LOAD_ERROR " + e.toString() + " line " + e.line;
}
var d = $.global.LookDecomposer;
if (!d) { return "LOAD_ERROR no panel handle"; }
lines.push("version=" + d.version);
lines.push("tabs=" + [d.ui.tabUpload, d.ui.tabAdjust, d.ui.tabGrade, d.ui.tabRegions].length);
lines.push("parts=" + d.ui.partRows.length);
lines.push("grade=" + d.ui.gradeRows.length);

function iconCount(api) {
    var row = api.bar.parent;
    var n = 0;
    for (var c = 0; c < row.children.length; c++) {
        if (row.children[c].type === "image") { n++; }
    }
    return n;
}
var noIcon = 0;
var sliderRows = d.ui.partRows.concat(d.ui.gradeRows);
for (var s = 0; s < sliderRows.length; s++) {
    if (sliderRows[s] && iconCount(sliderRows[s]) !== 1) { noIcon++; }
}
lines.push("rows_without_icon=" + noIcon);

var tabObjs = {"1 Upload": d.ui.tabUpload, "2 Adjust": d.ui.tabAdjust,
               "3 Grade": d.ui.tabGrade, "4 Regions": d.ui.tabRegions};
var names = ["1 Upload", "2 Adjust", "3 Grade", "4 Regions"];
for (var n = 0; n < names.length; n++) {
    var name = names[n];
    var view = null;
    for (var v = 0; v < d.fns.scrollViews.length; v++) {
        if (d.fns.scrollViews[v].name === name) { view = d.fns.scrollViews[v]; }
    }
    if (!view) { lines.push("scroll." + name + "=missing"); continue; }
    try {
        d.ui.tabs.selection = tabObjs[name];
        d.fns.showCurrentTab();
        var vp = view.body.size[1];
        var maxv = view.bar.maxvalue;
        var outside = 0, blank = 0, steps = 0, reached = {};
        for (var px = 0; px <= maxv; px += 10) {
            view.bar.value = px;
            d.fns.applyScroll(view);
            steps++;
            var shown = 0;
            for (var i = 0; i < view.rows.length; i++) {
                var y = view.rows[i].location[1];
                if (y > -5000) {
                    shown++;
                    reached[i] = true;
                    if (y < 0 || y + view.heights[i] > vp + 0.5) { outside++; }
                }
            }
            if (shown === 0) { blank++; }
        }
        var unreached = 0;
        for (var r = 0; r < view.rows.length; r++) { if (!reached[r]) { unreached++; } }
        view.bar.value = 0;
        d.fns.applyScroll(view);
        lines.push("scroll." + name + "=range:" + maxv + " steps:" + steps +
                   " outside:" + outside + " blank:" + blank + " unreached:" + unreached);
    } catch (e2) {
        lines.push("scroll." + name + "=error " + e2.toString());
    }
}
try { d.ui.win.close(); } catch (e3) { }
$.global.LookDecomposer = prevIsDocked ? prev : null;
return lines.join("\n");
"""


def installed_loader(version):
    # version_folders() is sorted oldest first; try the newest installed version first.
    for folder in reversed(install_panel.version_folders()):
        if version is None or folder.name == version:
            loader = install_panel.loader_path(folder)
            if loader.exists():
                return folder.name, loader
    return None, None


def source_version():
    m = re.search(r"var PANEL_VERSION = (\d+);", PANEL_SRC.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else None


def parse(text):
    values = {}
    scroll = {}
    for line in text.splitlines():
        if line.startswith("scroll."):
            name, _, rest = line[len("scroll."):].partition("=")
            scroll[name] = rest
        elif "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values, scroll


def check(values, scroll, expected_version):
    results = []

    def add(label, ok, detail=""):
        results.append((label, bool(ok), detail))

    add("panel version matches source", str(values.get("version")) == str(expected_version),
        "panel %s, source %s" % (values.get("version"), expected_version))
    add("four tabs", values.get("tabs") == str(EXPECTED_TABS), values.get("tabs", "?"))
    add("12 look sliders", values.get("parts") == str(EXPECTED_PARTS), values.get("parts", "?"))
    add("10 grade sliders", values.get("grade") == str(EXPECTED_GRADE), values.get("grade", "?"))
    add("every slider row has an icon", values.get("rows_without_icon") == "0",
        "rows without icon: %s" % values.get("rows_without_icon", "?"))

    for name in ["1 Upload", "2 Adjust", "3 Grade", "4 Regions"]:
        text = scroll.get(name, "missing")
        m = re.match(r"range:(\d+) steps:\d+ outside:(\d+) blank:(\d+) unreached:(\d+)", text)
        if not m:
            add("scroll %s" % name, False, text)
            continue
        rng, outside, blank, unreached = (int(x) for x in m.groups())
        add("scroll %s" % name, outside == 0 and blank == 0 and unreached == 0,
            "range %d px, outside %d, blank %d, unreached %d" % (rng, outside, blank, unreached))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ae", help="After Effects version folder, e.g. 26.5 (default: newest installed)")
    args = parser.parse_args(argv)

    version_folder, loader = installed_loader(args.ae)
    if loader is None:
        print("The panel is not installed for AE %s. Run: python3 -m look_decomposer.install_panel"
              % (args.ae or "any version"))
        return 2
    expected = source_version()
    if expected is None:
        print("Could not read PANEL_VERSION from %s" % PANEL_SRC)
        return 2

    code = JSX_TEMPLATE.replace("__LOADER__", json.dumps(str(loader)))
    try:
        response = ae_transport.run_jsx(code, 240)
    except SystemExit:
        print("After Effects is not reachable. Open After Effects and try again.")
        return 2
    if not response.get("ok") or response.get("error") not in (None, "None", ""):
        print("The check could not run in After Effects:")
        print(response.get("error") or response.get("result"))
        return 2
    text = str(response.get("result") or "")
    if text.startswith("LOAD_ERROR"):
        print(text)
        return 2

    values, scroll = parse(text)
    results = check(values, scroll, expected)
    print("Look Decomposer panel check (AE %s, panel version %s)" % (version_folder, values.get("version")))
    failed = 0
    for label, ok, detail in results:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, (" - " + detail) if detail else ""))
        if not ok:
            failed += 1
    print("%d of %d checks passed" % (len(results) - failed, len(results)))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
