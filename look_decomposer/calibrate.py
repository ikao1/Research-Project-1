#!/usr/bin/env python3
"""Calibrate analyzer estimators against real After Effects renders.

Renders single-effect sweeps of the base plate in AE (one comp, effect
added/removed per sweep, saveFrameToPng per setting), measures each PNG with
look_decomposer.stats, and writes look_decomposer/calibration.json — the
curves the analyzer inverts to turn image statistics into AE parameters.

Each sweep records a uniform set of metrics (luma quantiles, band masses,
midtone/dark/bright region colors, radial ratio, HF energy) so the analyzer
can chain per-effect response curves for its sequential inversion.

Usage:
    python3 -m look_decomposer.calibrate [--force]
"""

import argparse
import json
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from look_decomposer import ae_transport
    from look_decomposer.stats import Frame
else:
    from . import ae_transport
    from .stats import Frame

REPO_ROOT = Path(__file__).resolve().parent.parent
PLATE = REPO_ROOT / "test_stills" / "base_plate.png"
CALIB_DIR = REPO_ROOT / ".calib"
CALIB_JSON = Path(__file__).resolve().parent / "calibration.json"

# Luma quantiles recorded for every calibration frame. The analyzer's
# levels/exposure fit matches predicted quantile curves against these.
QUANTILES = [0.002, 0.01, 0.03, 0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92, 0.97, 0.99, 0.998]

# Tint sweep uses fixed map colors so the blend fraction k(strength) can be
# derived analytically from the measured region-color drift.
TINT_BLACK = [0.16, 0.29, 0.35]
TINT_WHITE = [0.91, 0.78, 0.55]

SWEEPS = [
    {
        "key": "exposure", "effect": "ADBE Exposure2",
        "params": {"ADBE Exposure2-0003": "stops"},
        "values": [-1.0, -0.75, -0.5, -0.25, 0.25, 0.5, 0.75, 1.0],
        "field": "stops",
    },
    {
        "key": "temperature", "effect": "ADBE Lumetri",
        "params": {"ADBE Lumetri-0007": "temperature"},
        "values": list(range(-100, 101, 20)),
        "field": "temperature",
    },
    {
        "key": "tint", "effect": "ADBE Lumetri",
        "params": {"ADBE Lumetri-0008": "tint"},
        "values": list(range(-60, 61, 15)),
        "field": "tint",
    },
    {
        "key": "saturation", "effect": "ADBE Color Balance (HLS)",
        "params": {"ADBE Color Balance (HLS)-0003": "amount"},
        "values": list(range(-100, 101, 20)),
        "field": "amount",
    },
    {
        "key": "vignette", "effect": "ADBE Lumetri",
        "params": {"ADBE Lumetri-0051": "amount"},
        "values": [-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
        "field": "amount",
    },
    {
        "key": "blur", "effect": "ADBE Gaussian Blur 2",
        "params": {"ADBE Gaussian Blur 2-0001": "radius_px",
                   "ADBE Gaussian Blur 2-0003": 1},
        "values": [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0],
        "field": "radius_px",
    },
    {
        "key": "noise_mono", "effect": "ADBE Noise2",
        "params": {"ADBE Noise2-0001": "amount", "ADBE Noise2-0002": 0},
        "values": [0, 10, 20, 30, 40, 50, 75, 100],
        "field": "amount",
    },
    {
        "key": "noise_color", "effect": "ADBE Noise2",
        "params": {"ADBE Noise2-0001": "amount", "ADBE Noise2-0002": 1},
        "values": [0, 10, 20, 30, 40, 50, 75, 100],
        "field": "amount",
    },
    {
        "key": "glow", "effect": "ADBE Glo2",
        "params": {"ADBE Glo2-0002": 180, "ADBE Glo2-0003": 15,
                   "ADBE Glo2-0004": "intensity"},
        "values": [0.1, 0.3, 0.5, 0.7, 0.9, 1.2, 1.5],
        "field": "intensity",
    },
    {
        "key": "levels_in_black", "effect": "ADBE Pro Levels2",
        "params": {"ADBE Pro Levels2-0004": "input_black"},
        "values": [0.0, 0.03, 0.06, 0.09, 0.12, 0.15],
        "field": "input_black",
    },
    {
        "key": "levels_in_white", "effect": "ADBE Pro Levels2",
        "params": {"ADBE Pro Levels2-0005": "input_white"},
        "values": [0.85, 0.88, 0.91, 0.94, 0.97, 1.0],
        "field": "input_white",
    },
    {
        "key": "levels_out_black", "effect": "ADBE Pro Levels2",
        "params": {"ADBE Pro Levels2-0007": "output_black"},
        "values": [0.0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.12],
        "field": "output_black",
    },
    {
        "key": "levels_out_white", "effect": "ADBE Pro Levels2",
        "params": {"ADBE Pro Levels2-0008": "output_white"},
        "values": [0.84, 0.88, 0.91, 0.94, 0.97, 1.0],
        "field": "output_white",
    },
    {
        "key": "tint_strength", "effect": "ADBE Tint",
        "params": {"ADBE Tint-0001": TINT_BLACK + [1],
                   "ADBE Tint-0002": TINT_WHITE + [1],
                   "ADBE Tint-0003": "strength"},
        "values": [0, 15, 30, 45, 60, 75, 90, 100],
        "field": "strength",
    },
]


def sweep_jsx(sweeps, plate, out_dir):
    lines = []
    lines.append('var p = app.project;')
    lines.append('if (!p) { p = app.newProject(); }')
    lines.append('var file = new File(%s);' % json.dumps(str(plate)))
    lines.append('var item = null;')
    lines.append('for (var i = 1; i <= p.numItems; i++) {')
    lines.append('    var it = p.item(i);')
    lines.append('    if (it instanceof FootageItem && it.file && it.file.fsName === file.fsName) { item = it; break; }')
    lines.append('}')
    lines.append('if (!item) { item = p.importFile(new ImportOptions(file)); }')
    lines.append('var dur = (isFinite(item.duration) && item.duration > 0) ? item.duration : 5;')
    lines.append('var fps = (isFinite(item.frameRate) && item.frameRate > 0) ? item.frameRate : 30;')
    lines.append('var comp = p.items.addComp("CAL — plate", item.width, item.height, 1, dur, fps);')
    lines.append('var layer = comp.layers.add(item);')
    lines.append('var group = layer.property("ADBE Effect Parade");')
    lines.append('var outDir = %s;' % json.dumps(str(out_dir)))
    lines.append('var folder = new Folder(outDir);')
    lines.append('if (!folder.exists) { folder.create(); }')
    lines.append('function snap(name) { comp.saveFrameToPng(0, new File(outDir + "/" + name + ".png")); }')
    for sweep in sweeps:
        key = sweep["key"]
        effect = sweep["effect"]
        lines.append('var fx = group.addProperty(%s);' % json.dumps(effect))
        for match_name, role in sweep["params"].items():
            if isinstance(role, str):
                continue
            lines.append('fx.property(%s).setValue(%s);' % (
                json.dumps(match_name), json.dumps(role)))
        for i, value in enumerate(sweep["values"]):
            tag = "%s_%02d" % (key, i)
            for match_name, role in sweep["params"].items():
                if isinstance(role, str):
                    lines.append('fx.property(%s).setValue(%s);' % (
                        json.dumps(match_name), json.dumps(value)))
            lines.append('snap(%s);' % json.dumps(tag))
        lines.append('fx.remove();')
    lines.append('comp.remove();')
    lines.append('return { rendered: true };')
    return "\n".join(lines)


def region01(rgb):
    if rgb is None:
        return None
    return [round(v / 255.0, 5) for v in rgb]


def frame_metrics(frame, plate, plate_stats):
    """Uniform per-frame measurements shared by every sweep.

    Region colors use the PLATE's luma for membership so the same scene
    pixels are measured in every frame regardless of tone shifts.
    """
    out = {
        "mean_luma": frame.mean_luma(),
        "quantiles": [round(frame.quantile(t), 5) for t in QUANTILES],
        "band_top": frame.band_mass(0.90, 1.01),
        "band_clip": frame.band_mass(0.98, 1.01),
        "band_bottom": frame.band_mass(0.0, 0.02),
        "radial_ratio": frame.radial_ratio(),
        "mid_color": region01(frame.masked_region_color(plate, 0.30, 0.70)),
        "mid_chroma": frame.masked_region_chroma(plate, 0.30, 0.70),
        "dark_color": region01(frame.masked_region_color(plate, 0.0, 0.12)),
        "bright_color": region01(frame.masked_region_color(plate, 0.85, 1.01)),
        "chroma_mean": frame.chroma_mean(),
    }
    out["mean_ratio"] = out["mean_luma"] / max(1e-6, plate_stats["mean_luma"])
    if plate_stats["mid_chroma"] > 1e-6:
        out["mid_chroma_ratio"] = out["mid_chroma"] / plate_stats["mid_chroma"]
    if plate_stats["band_top"] > 1e-6:
        out["band_top_ratio"] = out["band_top"] / plate_stats["band_top"]
    return out


def measure_plate(plate):
    detail_idx = Frame.detail_indices(plate.hf_window_values())
    stats = {
        "mean_luma": plate.mean_luma(),
        "channels": [round(v / 255.0, 5) for v in plate.channel_means()],
        "chroma": plate.chroma_mean(),
        "hf_energy": plate.hf_energy(),
        "hf_detail": plate.detail_hf(detail_idx),
        "noise_std": plate.noise_std(),
        "chroma_noise_std": plate.chroma_noise_std(),
        "radial_ratio": plate.radial_ratio(),
        "quantiles": [round(plate.quantile(t), 5) for t in QUANTILES],
        "band_top": plate.band_mass(0.90, 1.01),
        "band_clip": plate.band_mass(0.98, 1.01),
        "band_bottom": plate.band_mass(0.0, 0.02),
        "mid_color": region01(plate.region_color(0.30, 0.70)),
        "mid_chroma": plate.region_chroma(0.30, 0.70),
        "dark_color": region01(plate.region_color(0.0, 0.12)),
        "bright_color": region01(plate.region_color(0.85, 1.01)),
        "hf_detail_indices": detail_idx,
        "hf_window_count": len(plate.hf_window_values()),
    }
    return stats


def measure(out_dir):
    plate = Frame(PLATE)
    plate_stats = measure_plate(plate)
    detail_idx = plate_stats["hf_detail_indices"]
    plate_hf_detail = plate_stats["hf_detail"]
    plate_channels = plate.channel_means()

    calibration = {"plate": plate_stats, "quantiles": QUANTILES}

    for sweep in SWEEPS:
        key = sweep["key"]
        rows = {"field": sweep["field"], "values": list(sweep["values"])}
        for i, value in enumerate(sweep["values"]):
            frame = Frame(out_dir / ("%s_%02d.png" % (key, i)))
            m = frame_metrics(frame, plate, plate_stats)
            for metric, val in m.items():
                rows.setdefault(metric, []).append(round(val, 6) if isinstance(val, float) else val)
            if key in ("temperature", "tint"):
                rows.setdefault("channel_ratio", []).append(
                    [round(frame.channel_means()[c] / max(1.0, plate_channels[c]), 5)
                     for c in range(3)])
            elif key == "blur":
                rows.setdefault("hf_ratio", []).append(
                    round(frame.detail_hf(detail_idx) / max(1e-6, plate_hf_detail), 5))
            elif key in ("noise_mono", "noise_color"):
                rows.setdefault("hf_ratio", []).append(
                    round(frame.detail_hf(detail_idx) / max(1e-6, plate_hf_detail), 5))
                rows.setdefault("noise_std", []).append(round(frame.noise_std(), 5))
                rows.setdefault("chroma_noise_std", []).append(
                    round(frame.chroma_noise_std(), 5))
        calibration[key] = rows

    return calibration


def sweep_files(sweep):
    return [CALIB_DIR / ("%s_%02d.png" % (sweep["key"], i))
            for i in range(len(sweep["values"]))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true",
                        help="Re-render every sweep even if frames exist")
    args = parser.parse_args(argv)

    if not PLATE.exists():
        parser.error("Base plate missing: %s" % PLATE)

    to_render = []
    for sweep in SWEEPS:
        missing = [f for f in sweep_files(sweep) if not f.exists()]
        if args.force or missing:
            to_render.append(sweep)

    if to_render:
        CALIB_DIR.mkdir(exist_ok=True)
        print("Rendering %d sweep(s) in AE..." % len(to_render))
        code = sweep_jsx(to_render, PLATE, CALIB_DIR)
        response = ae_transport.run_jsx(code, timeout=280)
        if not response.get("ok"):
            print("AE script error:\n%s" % response.get("error"), file=sys.stderr)
            return 1

        wanted = [f for s in to_render for f in sweep_files(s)]
        deadline = time.time() + 120
        while time.time() < deadline:
            missing = [f for f in wanted if not f.exists()]
            if not missing:
                break
            time.sleep(1.0)
        missing = [f for f in wanted if not f.exists()]
        if missing:
            for f in missing[:5]:
                print("  missing: %s" % f.name, file=sys.stderr)
            return 1

    total = sum(len(s["values"]) for s in SWEEPS)
    print("Measuring %d calibration frames..." % total)
    calibration = measure(CALIB_DIR)
    calibration["fields"] = sorted({s["field"] for s in SWEEPS})
    CALIB_JSON.write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")
    print("Wrote %s" % CALIB_JSON)

    plate = calibration["plate"]
    print("plate: mean_luma=%.3f chroma=%.3f mid_chroma=%.3f hf_detail=%.4f radial=%.3f" % (
        plate["mean_luma"], plate["chroma"], plate["mid_chroma"],
        plate["hf_detail"], plate["radial_ratio"]))
    for key in ("exposure", "saturation", "vignette", "blur", "glow"):
        rows = calibration[key]
        vals = rows["values"]
        if key == "exposure":
            ys = rows["mean_ratio"]
        elif key == "saturation":
            ys = rows["mid_chroma_ratio"]
        elif key == "vignette":
            ys = [round(a / b, 3) for a, b in zip(rows["radial_ratio"],
                                                  [plate["radial_ratio"]] * len(vals))]
        elif key == "blur":
            ys = rows["hf_ratio"]
        else:
            ys = rows["band_top_ratio"]
        print("%-11s %s -> %s" % (key, vals, [round(y, 3) for y in ys]))
    for key in ("levels_in_black", "levels_in_white", "levels_out_black",
                "levels_out_white", "tint_strength"):
        rows = calibration[key]
        print("%-17s q(0.002)/q(0.998): %s" % (
            key, [("%.3f/%.3f" % (q[0], q[-1])) for q in rows["quantiles"]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
