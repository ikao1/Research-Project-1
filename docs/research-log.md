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

### 2026-11-23 — Startup loader tried, then removed: the panel appeared twice
- **Goal:** the Look Decomposer is there right after After Effects opens, with no
  menu digging.
- **Method:** `install_panel.py` wrote a startup loader into `Scripts/Startup/`
  in both the Preferences and Documents roots (AE runs both, depending on
  version), for AE 26.0 and 26.5. It loaded the panel source and opened it as a
  floating window.
- **Result:** After Effects restores the docked panel with the workspace, and the
  startup script opened a second floating window: the panel appeared twice. The
  startup loaders and the feature were removed again; the empty folders it made
  were cleaned up. The panel is opened by Window > Look Decomposer (docked,
  restored with the workspace) or File > Scripts > Open Look Decomposer.
- **Next step:** none. Revisit only if the user asks for auto-open again, in
  which case the loader must detect the docked instance first.

### 2026-11-23 — Upload tab simplified: the footage upload section is gone
- **Goal:** drop the "B. Footage to grade" section from tab 1.
- **Method:** Panel v18. Tab 1 keeps only the reference look upload and the
  setup check; footage is imported by the user in After Effects and picked up
  with "Use this composition". Status texts and the no-target messages were
  reworded to match. The addFootageFiles machinery stays in the code (used by
  the tests) but is no longer reachable from the panel.
- **Result:** `panel_check.py` 9 of 9.
- **Next step:** none.

### 2026-11-23 — A launcher button with an icon, and no auto-open panel
- **Goal:** a button the user clicks to open the tool (the panel must not open
  by itself at launch).
- **Method:** a small always-on-top palette window with an icon button (new
  `launch.png` lightning icon drawn by make_icons.py). The button evals the
  panel source and opens the full window when clicked. Installed by
  install_panel.py as File > Scripts > Look Decomposer Button, and a startup
  loader shows only the button window when After Effects starts - the panel
  itself never auto-opens. Duplicate presses reuse the same button window
  through $.global.
- **Result:** tested live in AE 26.5: button window, icon button, and
  click-open all work (panel v18 opened). Note: After Effects cannot add a
  button to its own toolbar next to the Home button from a script; this
  floating icon button is the closest possible, and it can be dragged anywhere.
- **Next step:** the user drags the button where they want it. A docked panel
  tab may still return at launch if it is saved in the workspace; close the tab
  and save the workspace to stop that.

### 2026-11-23 — Launcher button replaced by an After Effects workspace
- **Goal:** reach the Look Decomposer through a workspace instead of the
  floating launcher button.
- **Method:** removed the launcher button and its startup loaders (both files
  per version, 26.0 and 26.5) and reverted install_panel.py, make_icons.py and
  the launch icon. After Effects has no script API for workspaces, so the
  workspace is made by hand: Window > Look Decomposer to dock the panel,
  arrange it, then Window > Workspace > Save as New Workspace; switching to it
  brings the panel back. The Window-menu panel loader stays installed.
- **Result:** no launcher artifacts left on disk; only the Window menu panel
  loader and File > Scripts > Open Look Decomposer remain.
- **Next step:** the user saves the workspace. Note the workspace also decides
  whether the panel comes back when After Effects launches.
