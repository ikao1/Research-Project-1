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

### 2026-11-23 — Panel UI polish and the "Use this composition" button
- **Goal:** A cleaner look for the whole panel, and an obvious one-press way to
  start the tool when a composition is open.
- **Method:** Panel v17. Dark header band (title + version), tinted status box,
  colored section headings, accent-colored primary buttons (Upload reference,
  Upload footage, Create auto-masked region). A big "Use this composition" button
  sits at the top of every tab: it targets the selected footage layer in the open
  comp (otherwise the topmost), applies a loaded reference look when the layer has
  no look yet, selects the layer, and jumps to tab 2. Docked scroll cap now reads
  the tabs' real position instead of a fixed chrome constant.
- **Result:** `panel_check.py` 9 of 9. Live test of the button in AE 26.5: status
  text correct, the layer's token written to its comment, the layer selected, the
  panel on tab 2; the test comp and footage were removed afterwards.
- **Next step:** after an After Effects restart, check the docked panel's v17
  look, the button, and the scroll bar. Then the overdue analyzer work (glow,
  exposure and gamma, split-tone strength).

### 2026-11-23 — Startup loader: the panel opens when After Effects launches
- **Goal:** the Look Decomposer is there right after After Effects opens, with no
  menu digging.
- **Method:** `install_panel.py` now also writes a startup loader into
  `Scripts/Startup/` in both the Preferences and Documents roots (AE runs both,
  depending on version), for AE 26.0 and 26.5. It loads the panel source and
  opens it as a floating window; failures are logged with `$.writeln` instead of
  an alert.
- **Result:** install and `--status` verified; all four startup loaders present.
  The auto-open itself needs an After Effects restart to be seen.
- **Next step:** restart After Effects and confirm the window opens on its own.
