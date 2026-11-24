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

### 2026-11-23 — Assignment deliverables: README, demo video, presentation notes
- **Goal:** everything the Nov 23 deadline asks for: repo link, README with the
  required sections, a 1-3 minute recording linked from the README, and a
  walk-through.
- **Method:** README rewritten (what I set out to do, what I made, how to run
  it, what I learned, what doesn't work, what's next, how the project changed).
  The demo video is 75 s, composed and rendered by After Effects itself: the
  rebuilt frames come from the tool's own engine (`build.py --mode flat`), then
  a comp steps reference → raw → split rebuild → full rebuild → side-by-side
  proof → end card, exported H.264 1280x720. macOS screen capture is blocked
  (no Screen Recording permission for Terminal, QuickTime Player, or Chrome,
  even after grants - in-app rendering is the permission-free equivalent that
  the Blender project used too). `docs/demo-script.md` holds the 5-7 min
  presentation with a deep dive on one part. AE project cleaned to just the
  demo comp; not saved.
- **Result:** video verified frame-by-frame with pixel statistics (each
  segment shows the right content; the reference-vs-rebuild split halves match,
  the engine's rebuild reproduces the reference). Committed and pushed.
- **Next step:** present Tue Nov 24; optionally swap in a true screen
  recording if Screen Recording permission ever works.

### 2026-11-24 — Panel v19: professional pass on Upload and Regions
- **Goal:** what a professional would need from the reference workflow and the
  region tooling.
- **Method:** Tab 1 gained a reference preview thumbnail (PIL thumbnail
  module), a recent-references dropdown that re-applies earlier analyses
  without re-analyzing, Save/Load look preset JSON files, and "Apply to all"
  for every footage layer in the comp. Tab 4 gained timeline selection sync
  (picking a region selects its layer so the mask shows), [on]/[off] list
  prefixes with an On/off button, Duplicate (with its own matte copy for auto
  regions), Rename via a small dialog, Move up/down through the layer stack,
  and Update mask, which re-runs the stored auto mask. Scroll margin went 8 ->
  14 px so the panel check's 10 px sampling reaches every row.
- **Result:** `panel_check.py` 9 of 9. Live-tested in AE 26.5:
  thumbnail/history/apply-to-all, and add/select/toggle/duplicate/move/
  update-mask (all passed after fixes; test items removed afterwards). Two
  real bugs found and fixed: Move up was a no-op (moveAfter instead of
  moveBefore), and Update mask removed its own new matte and then worked on
  the removed layer - which crashed After Effects twice. AE 26.5 also crashed
  once without an explained cause and auto-recovers autosaves, so the open
  project can change without warning. Dialog-driven paths (Rename, Save/Load
  preset file dialogs) were not driven by the agent.
- **Next step:** restart After Effects and check the docked v19 panel; drive
  the dialog buttons once by hand.

### 2026-11-24 — Tabs 1 and 4 tidied up
- **Goal:** make Upload and Regions nicer to look at.
- **Method:** Tab 1: the reference name (bold) and the Recent dropdown share
  one row, the preview image sits under them, and the three preset buttons
  have equal widths. Tab 4: taller region list, all management buttons sized
  evenly in three tidy rows, and consistent full-width dropdowns for Select,
  Shape, Colors and Blend.
- **Result:** `panel_check.py` 9 of 9.
- **Next step:** visual check in the docked panel after a restart.

### 2026-11-24 — Icons on Upload, and a full feature test (41 checks)
- **Goal:** icons in tab 1, a nicer look, and proof that every slider and
  function works.
- **Method:** six new icons (upload, clock, disk, folder, layers,
  check_circle) drawn by make_icons.py and placed in tab 1 rows. Tab titles
  got periods (1. Upload...). A new tool, `tools/panel_feature_test.py`,
  drives every feature in live After Effects against a scratch comp it creates
  and removes: reference analysis/thumbnail/history, Use this composition,
  Apply to all, all 12 look sliders with effect-parameter readback (Exposure
  stops, blur radius, grain, vignette, split-tone strength), part toggles,
  Strength scaling (1.2 -> 0.6 stops at 50%), all 10 grade sliders with
  Lumetri readback, Remove/Reset grade, and the full region set (settings,
  hue/value/sat effects, opacity, blend, mask, on/off, duplicate, move,
  auto mask, Update mask).
- **Result:** 9 of 9 panel checks and 41 of 41 feature checks pass. The only
  test fix needed was the BlendingMode comparison (enum, not string).
- **Next step:** none pending on the panel; drive the dialog buttons
  (Rename, Save/Load preset) once by hand.

### 2026-11-24 — Apply reference fixed: the reference survives restarts
- **Goal:** "Apply reference" in tab 2 seemed to do nothing.
- **Method:** The button itself was verified working (overrides cleared,
  sliders reset to reference values, effects rebuilt - exported to fns and
  tested live). The real gap: the reference was per-window session state, so a
  second panel window, an After Effects restart, or a crash recovery lost it
  and the button had nothing to apply. Panel v22 now persists the current
  reference (name, look, confidence, summary, thumbnail path) to
  ~/Library/Application Support/LookDecomposer/reference.json on every set
  (upload, history pick, preset load), and every new panel instance restores
  it into the reference and the history.
- **Result:** live test: upload, close the window, open a fresh panel - the
  reference, history and label come back, and Apply reference applies it at
  once. panel_check 9 of 9, feature test 41 of 41.
- **Next step:** the user re-checks their real workflow (docked panel).
