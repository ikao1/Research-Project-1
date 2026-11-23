# Presentation notes (Tue Nov 24, 5–7 min)

Companion to `docs/demo.mp4`. The video shows the flow below; these notes are
the talking points, including one part explained in depth (marked **DEEP DIVE**)
for the "walk me through one part of it" question.

## 0. The idea (30 s)

A flattened movie still doesn't tell you how it was graded. My tool takes a
reference image, estimates the look (exposure, contrast, color, grain, blur,
vignette, ...), and rebuilds it in After Effects as **named layers and live
sliders** — not a preset, not a LUT, but an editable starting point you can
steer. Pipeline: `reference → Python analyzer → analysis JSON → AE panel/builder
→ editable comp + how-to guide`.

## 1. The reference and the analysis (60 s)

- Show the reference still (a warm sunset still in the demo).
- The panel's Upload tab analyzes it in a few seconds; the result lists every
  aspect it found and a confidence word.
- Show the generated how-to guide (`guide.py` output): each step quotes the
  analyzer's reason and confidence. Honesty is a feature: the schema carries
  notes per estimate, and confidence is scaled down when the neutral base
  plate isn't available.

## 2. Rebuilding the look in After Effects (60 s)

- Press **Use this composition**: the panel finds the footage layer, applies
  the look, selects the layer, and jumps to the Adjust tab.
- The comp now has named adjustment layers (Look: Exposure, Look: Tint, ...).
- Drag sliders: Brightness, Warm/cool, Glow, Film grain. Uncheck a box to turn
  a part off; Strength scales the whole look.
- Lumetri grade (tab 3) and regions with auto masks (tab 4) follow.

## 3. DEEP DIVE — how the analyzer measures one field: vignette (90 s)

Pick one concrete path and explain it end to end:

1. **Calibration.** The base plate has known regions: a sky gradient, corners
   that are meant to stay uniform, and a mid-gray surround. The analyzer
   samples the corners vs the center of the plate *before* the look and *in the
   reference image*.
2. **Measurement.** Corner luminance is compared to the center through a
   radial falloff model. A negative center-to-corner gradient = darkening
   vignette; the magnitude maps to Lumetri's Vignette `amount` (-5..5), with
   midpoint/feather fitted from how quickly the falloff ramps.
3. **Why a model, not a lookup.** A lookup can't separate vignette from
   exposure; the radial model can, and its parameters map 1:1 to AE's own
   Vignette parameters — that's why the rebuilt comp gets a real *named
   adjustment layer*, not a flattened pixel patch.
4. **The check.** The ground-truth set renders each look with After Effects
   itself and `score.py` compares the analyzer's JSON against the known truth
   field by field (vignette: 0.203 mean normalized error — mid-table; the
   weakest fields are glow and exposure).

The same story repeats per aspect: measure against the calibrated plate, fit a
parametric model, emit schema JSON, and the AE engine turns that JSON into an
adjustment layer whose sliders re-drive the *same* parameters the model used.

## 4. Verification (60 s)

- Ten ground-truth looks rendered by AE itself; parameter readback matches the
  JSON exactly (0 mismatches).
- Analyzer score: **0.150 mean normalized error**, down from 0.194.
- Panel: 9 of 9 automated checks; the transfer test showed the reference must
  be applied to raw footage (error 19.3 vs 22.4 when double-grading).
- Screen capture is blocked on this Mac, so claims are backed by numbers.

## 5. Honest limits and next (45 s)

- Video gets one frame's look today; subject masks are photo-focused.
- Weakest fields: glow, exposure stops/gamma, split-tone strength.
- Next: region-wise estimation for those three, temporal analysis for video,
  and a UXP panel for real docked scrolling.

## If asked "what does this line do?"

Use `look_decomposer/analyzer.py` (fit + gate per aspect), the panel's
`useThisComposition()` in `ae_panel/LookDecomposer.jsx`, or the engine's
`LOOKFX.applyAspect()` in `ae/look_fx.jsx`. The repo is organized so each part
is a small, named module — walk to it and read it.
