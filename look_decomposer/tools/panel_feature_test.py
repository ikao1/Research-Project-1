#!/usr/bin/env python3
"""Exercise every Look Decomposer panel feature in the open After Effects.

Runs each feature against a scratch composition (created by this script and
removed afterwards) and checks the real layer/effect state, not just the UI:

  - reference analysis: thumbnail, history, preview image, summary
  - Use this composition, Apply reference to all
  - every look slider (12) writes its override and builds its effect
  - toggling a part off removes its effect and back on restores it
  - Strength scales the look
  - every grade slider (10) writes the grade and drives the Lumetri effect
  - Remove look keeps the grade; Reset grade clears it
  - regions: add, hue/value/sat/opacity/size/feather/position/shape/channel/
    blend, on/off, duplicate, move, auto mask + Update mask

Needs After Effects open with the panel installed. Uses the installed loaders.
Exit codes: 0 all checks pass, 1 a check failed, 2 After Effects unavailable.

Usage:
    python3 look_decomposer/tools/panel_feature_test.py
    python3 look_decomposer/tools/panel_feature_test.py --ae 26.5
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

PLATE = REPO / "test_stills" / "base_plate.png"
REFERENCE = REPO / "test_stills" / "renders" / "warm_sunset.png"
COMP_NAME = "LD FEATURE TEST"

# 12 part sliders in panel order: index, override value to set, aspect, field.
PARTS = [
    (0, 1.2, "exposure", "stops"),
    (1, 0.10, "levels", "input_black"),
    (2, 0.90, "levels", "input_white"),
    (3, 0.05, "levels", "output_black"),
    (4, 30, "white_balance", "temperature"),
    (5, -20, "white_balance", "tint"),
    (6, 25, "saturation", "amount"),
    (7, 60, "split_tone", "strength"),
    (8, 8, "blur", "radius_px"),
    (9, 1.2, "glow", "intensity"),
    (10, -2, "vignette", "amount"),
    (11, 40, "grain", "amount"),
]

JSX_TEMPLATE = r"""
var lines = [];
var prev = $.global.LookDecomposer;
var prevIsDocked = false;
try { prevIsDocked = !!(prev && prev.ui && prev.ui.win instanceof Panel); } catch (e0) { }
if (!prevIsDocked) {
    try { if (prev && prev.ui && prev.ui.win) { prev.ui.win.close(); } } catch (e1) { }
}
$.global.LookDecomposer = null;
try {
    $.evalFile(new File(__LOADER__));
} catch (e) {
    return "LOAD_ERROR " + e.toString() + " line " + e.line;
}
var d = $.global.LookDecomposer;
if (!d || !d.ui || !d.ui.win) { return "LOAD_ERROR no panel handle"; }

function check(name, ok, detail) {
    lines.push((ok ? "PASS " : "FAIL ") + name + (detail ? " - " + detail : ""));
}
function effectOf(layer, namePart) {
    var group = layer.property("ADBE Effect Parade");
    for (var i = 1; i <= group.numProperties; i++) {
        if (group.property(i).name.indexOf(namePart) === 0) { return group.property(i); }
    }
    return null;
}
function fxValue(layer, namePart, matchName) {
    var fx = effectOf(layer, namePart);
    if (!fx) { return "no-fx"; }
    try {
        var v = fx.property(matchName).value;
        return Math.round(v * 1000) / 1000;
    } catch (e) { return "no-prop"; }
}
function lookup(comp) {
    var r = {footage: null, regions: [], mattes: []};
    for (var i = 1; i <= comp.numLayers; i++) {
        var ly = comp.layer(i);
        var s = d.fns.regionSettingsOf(ly);
        if (s) { r.regions.push(ly); }
        else if (String(ly.name).indexOf("Matte") === 0) { r.mattes.push(ly); }
        else if (!ly.adjustmentLayer && !ly.isTrackMatte && ly.source instanceof FootageItem && ly.name !== "Matte") {
            if (!r.footage) { r.footage = ly; }
        }
    }
    return r;
}

/* ------- scratch scene ------- */
var img = app.project.importFile(new ImportOptions(__PLATE__));
var comp = app.project.items.addComp(__COMP__, img.width, img.height, img.pixelAspect, 5, 30);
var l1 = comp.layers.add(img);
var l2 = comp.layers.add(img);
comp.openInViewer();
check("scratch comp created", comp && l1 && l2, comp.name + " layers=" + comp.numLayers);

/* ------- tab 1: reference flow ------- */
try {
    d.fns.setReference(new File(__REF__));
    check("setReference", d.state.reference && d.state.reference.name === "warm_sunset",
          d.state.reference ? d.state.reference.name : "null");
    check("thumbnail file", d.state.reference && d.state.reference.thumb && new File(d.state.reference.thumb).exists);
    check("reference label", d.ui.refLabel && String(d.ui.refLabel.text).indexOf("warm_sunset") >= 0,
          d.ui.refLabel.text);
    check("history entry", d.state.refHistory.length >= 1, "length=" + d.state.refHistory.length);
    check("summary text", d.ui.refResult && String(d.ui.refResult.text).length > 20);
    d.ui.refHistory.selection = 1;
    d.fns.onHistorySelect();
    check("history re-apply", d.state.reference.name === "warm_sunset");
} catch (e) {
    check("reference flow", false, e.toString() + " line " + e.line);
}

/* ------- Use this composition + apply to all ------- */
try {
    d.fns.useThisComposition();
    check("useThisComposition target", d.state.workToken && d.fns.targetLayer() && d.fns.targetLayer().name === "base_plate.png");
    d.fns.applyReferenceToAll();
    var st1 = d.fns.loadLookState(l1);
    var st2 = d.fns.loadLookState(l2);
    check("apply to all", !!st1.analysis && !!st2.analysis,
          "l1=" + (st1.analysis ? "look" : "none") + " l2=" + (st2.analysis ? "look" : "none"));
} catch (e) {
    check("apply-to-all flow", false, e.toString() + " line " + e.line);
}

/* ------- look sliders (12) ------- */
try {
    for (var sl = 1; sl <= comp.numLayers; sl++) { comp.layer(sl).selected = false; }
    l1.selected = true;
    d.fns.onStrength(100);
    var partOk = 0, partBad = [];
    for (var p = 0; p < __PARTS__.length; p++) {
        var pi = __PARTS__[p][0], val = __PARTS__[p][1], aspect = __PARTS__[p][2], field = __PARTS__[p][3];
        d.fns.onPartChange(pi, val);
        var st = d.fns.loadLookState(l1);
        var key = __PARTKEYS__[pi];
        if (st.overrides[key] === Math.round(val * 1000) / 1000) { partOk++; }
        else { partBad.push(key + "=" + st.overrides[key]); }
    }
    check("12 slider overrides stored", partOk === 12, "bad: " + partBad.join(","));
    check("exposure fx", fxValue(l1, "Look: Exposure", "ADBE Exposure2-0003") === 1.2,
          "stops=" + fxValue(l1, "Look: Exposure", "ADBE Exposure2-0003"));
    check("blur fx", fxValue(l1, "Look: Gaussian Blur", "ADBE Gaussian Blur 2-0001") === 8,
          "radius=" + fxValue(l1, "Look: Gaussian Blur", "ADBE Gaussian Blur 2-0001"));
    check("grain fx", fxValue(l1, "Look: Grain", "ADBE Noise2-0001") === 40,
          "amount=" + fxValue(l1, "Look: Grain", "ADBE Noise2-0001"));
    check("vignette fx", fxValue(l1, "Look: Vignette", "ADBE Lumetri-0051") === -2,
          "amount=" + fxValue(l1, "Look: Vignette", "ADBE Lumetri-0051"));
    check("split tone fx", fxValue(l1, "Look: Split Tone", "ADBE Tint-0003") === 60,
          "strength=" + fxValue(l1, "Look: Split Tone", "ADBE Tint-0003"));

    d.fns.onPartToggle(8, false);
    check("toggle off removes fx", effectOf(l1, "Look: Gaussian Blur") === null);
    d.fns.onPartToggle(8, true);
    check("toggle on restores fx", effectOf(l1, "Look: Gaussian Blur") !== null);

    d.fns.onStrength(50);
    check("strength scales fx", fxValue(l1, "Look: Exposure", "ADBE Exposure2-0003") === 0.6,
          "stops=" + fxValue(l1, "Look: Exposure", "ADBE Exposure2-0003"));
    d.fns.onStrength(100);
} catch (e) {
    check("look slider flow", false, e.toString() + " line " + e.line);
}

/* ------- grade sliders (10) ------- */
try {
    var gOk = 0, gBad = [];
    for (var g = 0; g < __GRADE_KEYS__.length; g++) {
        d.fns.onGradeChange(g, g + 1);
        var st = d.fns.loadLookState(l1);
        if (st.grade && st.grade[__GRADE_KEYS__[g]] === g + 1) { gOk++; }
        else { gBad.push(__GRADE_KEYS__[g]); }
    }
    check("10 grade values stored", gOk === 10, "bad: " + gBad.join(","));
    check("grade exposure fx", fxValue(l1, "Look: Grade", "ADBE Lumetri-0011") === 1, "v=" + fxValue(l1, "Look: Grade", "ADBE Lumetri-0011"));
    check("grade saturation fx", fxValue(l1, "Look: Grade", "ADBE Lumetri-0020") === 7, "v=" + fxValue(l1, "Look: Grade", "ADBE Lumetri-0020"));

    d.fns.removeLook();
    var stR = d.fns.loadLookState(l1);
    check("remove look clears analysis", stR && !stR.analysis);
    check("remove look keeps grade", stR && stR.grade !== null);
    d.fns.resetGrade();
    stR = d.fns.loadLookState(l1);
    check("reset grade clears it", stR && !stR.grade);
} catch (e) {
    check("grade flow", false, e.toString() + " line " + e.line);
}

/* ------- regions ------- */
try {
    d.fns.refreshRegions();
    var r0 = d.state.regionTokens.length;
    d.fns.addRegion();
    check("add region", d.state.regionTokens.length === r0 + 1, "regions=" + d.state.regionTokens.length);
    d.ui.regionList.selection = 0;
    var selNames = [];
    for (var sn = 0; sn < comp.selectedLayers.length; sn++) { selNames.push(comp.selectedLayers[sn].name); }
    check("select region selects layer", selNames.join(",").indexOf("Region:") === 0, selNames.join(","));

    d.ui.regColor.selection = 4;
    d.ui.regHue.setValue(35);
    d.ui.regValue.setValue(-25);
    d.ui.regSat.setValue(50);
    d.ui.regOpacity.setValue(70);
    d.ui.regArea.value = true;
    d.ui.regShape.selection = 1;
    d.ui.regSize.setValue(60);
    d.ui.regFeather.setValue(30);
    d.ui.regX.setValue(10);
    d.ui.regY.setValue(-10);
    d.ui.regBlend.selection = 3;
    d.fns.onRegionChange();
    var r = lookup(comp).regions[0];
    var s = d.fns.regionSettingsOf(r);
    check("region settings saved", s.channel === 5 && s.hue === 35 && s.value === -25 && s.sat === 50 &&
          s.opacity === 70 && s.shape === "rectangle" && s.size === 60 && s.feather === 30 &&
          s.x === 10 && s.y === -10 && s.blend === "OVERLAY",
          "channel=" + s.channel + " blend=" + s.blend);
    var hs = effectOf(r, "Region: hue and value");
    check("region fx hue", Math.round(hs.property("ADBE HUE SATURATION-0004").value) === 35);
    check("region fx value", Math.round(hs.property("ADBE HUE SATURATION-0006").value) === -25);
    check("region fx sat", Math.round(hs.property("ADBE HUE SATURATION-0005").value) === 50);
    check("region opacity", Math.round(r.opacity.value) === 70);
    check("region blend mode", r.blendingMode === BlendingMode.OVERLAY,
          "blend=" + String(r.blendingMode));
    check("region mask", r.property("ADBE Mask Parade").numProperties >= 1);

    d.fns.toggleRegion();
    r = lookup(comp).regions[0];
    check("region off", r.enabled === false);
    check("list shows off", String(d.ui.regionList.items[0].text).indexOf("[off]") === 0);
    d.fns.toggleRegion();
    r = lookup(comp).regions[0];
    check("region on", r.enabled === true);

    var before = d.state.regionTokens.length;
    d.fns.duplicateRegion();
    check("duplicate region", d.state.regionTokens.length === before + 1);

    d.ui.regionList.selection = 1;
    var name1 = String(d.ui.regionList.items[0].text);
    d.fns.moveRegion(-1);
    check("move region up", String(d.ui.regionList.items[0].text) !== name1);

    d.ui.autoMode.selection = 2;
    var autoBefore = d.state.regionTokens.length;
    d.fns.createAutoRegion();
    check("auto region", d.state.regionTokens.length === autoBefore + 1);
    var mattesBefore = lookup(comp).mattes.length;
    d.fns.updateAutoMask();
    check("update mask", lookup(comp).mattes.length === mattesBefore,
          "mattes=" + lookup(comp).mattes.length + " (was " + mattesBefore + ")");
} catch (e) {
    check("region flow", false, e.toString() + " line " + e.line);
}

/* ------- cleanup ------- */
try {
    var cleanSolids = [];
    for (var rl = 1; rl <= comp.numLayers; rl++) {
        var rly = comp.layer(rl);
        if (d.fns.regionSettingsOf(rly)) {
            var rsrc = rly.source;
            if (rsrc instanceof FootageItem) { cleanSolids.push(rsrc); }
        }
    }
    comp.remove();
    for (var ci = 0; ci < cleanSolids.length; ci++) {
        try { cleanSolids[ci].remove(); } catch (e) { }
    }
    try { img.remove(); } catch (e) { }
    for (var j = app.project.numItems; j >= 1; j--) {
        var it = app.project.item(j);
        var isMatte = false;
        try { isMatte = !!it.file && String(it.file.fsName).indexOf("LookDecomposer/Mattes") >= 0; } catch (e) { }
        if (isMatte) {
            try { it.remove(); } catch (e) { }
        }
    }
    var names = [];
    for (var k = 1; k <= app.project.numItems; k++) { names.push(app.project.item(k).name); }
    check("scratch removed", names.join(",").indexOf(__COMP__) < 0, names.join(",").substring(0, 120));
    d.ui.win.close();
} catch (e) {
    lines.push("FAIL cleanup - " + e.toString());
}
$.global.LookDecomposer = prevIsDocked ? prev : null;
return lines.join("\n");
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ae", help="After Effects version folder, e.g. 26.5 (default: newest installed)")
    args = parser.parse_args(argv)

    version_folder, loader = None, None
    for folder in reversed(install_panel.version_folders()):
        if args.ae is None or folder.name == args.ae:
            candidate = install_panel.loader_path(folder)
            if candidate.exists():
                version_folder, loader = folder.name, candidate
                break
    if loader is None:
        print("The panel is not installed for AE %s. Run: python3 -m look_decomposer.install_panel"
              % (args.ae or "any version"))
        return 2

    source = REPO / "look_decomposer" / "ae_panel" / "LookDecomposer.jsx"
    src = source.read_text(encoding="utf-8")
    parts_block = src[src.index("var PARTS = ["):]
    parts_block = parts_block[:parts_block.index("];")]
    part_keys = re.findall(r'{key: "([^"]+)",', parts_block)
    grade_block = src[src.index("var GRADE_CONTROLS = ["):]
    grade_block = grade_block[:grade_block.index("];")]
    grade_keys = re.findall(r'{key: "([^"]+)",', grade_block)
    if len(part_keys) != 12:
        print("Expected 12 part keys, found %d: %s" % (len(part_keys), part_keys))
        return 2
    if len(grade_keys) != 10:
        print("Expected 10 grade keys, found %d: %s" % (len(grade_keys), grade_keys))
        return 2

    code = (JSX_TEMPLATE
            .replace("__LOADER__", json.dumps(str(loader)))
            .replace("__PLATE__", json.dumps(str(PLATE)))
            .replace("__REF__", json.dumps(str(REFERENCE)))
            .replace("__COMP__", json.dumps(COMP_NAME))
            .replace("__PARTKEYS__", json.dumps(part_keys))
            .replace("__GRADE_KEYS__", json.dumps(grade_keys))
            .replace("__PARTS__", json.dumps(PARTS)))
    try:
        response = ae_transport.run_jsx(code, 280)
    except SystemExit:
        print("After Effects is not reachable. Open After Effects and try again.")
        return 2
    if not response.get("ok") or response.get("error") not in (None, "None", ""):
        print("The test could not run in After Effects:")
        print(response.get("error") or response.get("result"))
        return 2
    text = str(response.get("result") or "")
    if text.startswith("LOAD_ERROR"):
        print(text)
        return 2

    print("Look Decomposer feature test (AE %s)" % version_folder)
    passed = failed = 0
    for line in text.splitlines():
        print("  " + line)
        if line.startswith("PASS "):
            passed += 1
        elif line.startswith("FAIL "):
            failed += 1
    print("%d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
