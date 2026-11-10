# Research Log

Record findings, hypotheses, and experiment results here.

## Entry template

### YYYY-MM-DD — Title
- **Goal:**
- **Method:**
- **Result:**
- **Next step:**

### 2026-11-09 — Nov 10 milestone: technical spike complete
- **Goal:** Test set of ~10 reference stills, an AE script that builds a comp
  with named adjustment layers + sliders, and the analysis schema (per
  docs/proposal.md).
- **Method:** Probed AE 26.5 for effect match names/param ranges through the
  MCP bridge (Exposure, Levels, Lumetri, Color Balance (HLS), Tint, Gaussian
  Blur, Glow, Noise, Slider Control). Built `look_decomposer/`:
  `ae/look_fx.jsx` engine, schema v1.0 (`schema/analysis.schema.json` +
  `validate.py`), a deterministic PIL base plate with calibration regions,
  and 10 look JSONs rendered to ground-truth PNGs by AE itself (flat mode).
- **Result:** All ten looks render; parameter readback of every GEN comp
  matches its JSON exactly (0 mismatches). Edit mode builds `LOOK — <slug>`
  comps with named adjustment layers and a `LOOK CONTROLS` null whose
  sliders drive the stack via expressions (6/6 wired on warm_sunset).
  Two AE quirks discovered and handled: Hue/Saturation parameters cannot
  hold expressions (switched to Color Balance (HLS), verified visually
  identical), and Noise's "Noise Type" menu is 0=mono/1=color (AE defaults
  to color noise).
- **Next step:** Nov 17 — analyzer (PIL statistics on calibration regions),
  rule-based guide generation, scoring against the ground-truth pairs.

### 2026-11-10 — Panel, auto masks, and the transfer test
- **Goal:** a usable After Effects panel that applies a reference look to uploaded footage
  and lets the user adjust it; auto masks for local edits.
- **Method:** ScriptUI panel (v16) tested in After Effects by reading rendered pixels and
  effect values. The reference look was applied to the raw base plate and, for comparison,
  to the already-graded still. Auto masks were tested on a photo with several people.
- **Result:**
  - The look on the raw plate is closer to the reference render (mean absolute error 19.3,
    raw plate 24.4). The same look on the graded still gives 22.4 and is over-saturated
    (colour spread 85 vs 64). The reference must be applied to the ungraded footage.
  - Analyzer on the 10 test looks: mean normalized error 0.150 (was 0.194 before the
    split-tone gate and the crash fix).
  - Subject mask separated both foreground characters on a photo; the People mode missed
    the illustrated characters.
- **Next step:** verify the docked panel's scroll bar after restarting After Effects; then
  the Nov 17 analyzer work (glow, exposure and gamma, split-tone strength).
