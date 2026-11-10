# Project notes for coding agents

Last updated: 2026-11-10. Keep this file short. Update it instead of adding duplicates.

## What this project is
Research Project 1, the *Look Decomposer*. It analyzes a reference still or video, then
rebuilds its look inside After Effects as sliders the user can edit.
- Repo: github.com/ikao1/Research-Project-1, branch `main`.
- Plan: `docs/proposal.md`. Lab notebook: `docs/research-log.md`.
- Project guide: `look_decomposer/README.md`.

## Where things are
- `look_decomposer/analyzer.py`: estimates a look from an image.
  `python3 -m look_decomposer.analyzer <image> --reference test_stills/base_plate.png -o out.json`
- `look_decomposer/ae/look_fx.jsx`: After Effects effect engine (used by the panel and builder).
- `look_decomposer/ae_panel/LookDecomposer.jsx`: the panel (four tabs). Icons are in
  `ae_panel/icons/`, drawn by `tools/make_icons.py`.
- `look_decomposer/install_panel.py`: puts the panel loader in the After Effects 26.0 and
  26.5 ScriptUI Panels folders. Options: `--status`, `--uninstall`.
- `look_decomposer/automask.py` with `tools/automask_vision.swift`: auto masks.
  `python3 -m look_decomposer.automask --build` compiles the Vision helper into
  `look_decomposer/bin/` (git-ignored, machine-specific).
- `look_decomposer/guide.py` (how-to markdown) and `look_decomposer/score.py` (scoring
  against `test_stills/`).
- `ae_mcp/`: the After Effects bridge (AppleScript DoScript). `look_decomposer/ae_transport.py`
  sends JSX through it.
- `look_decomposer/tools/panel_check.py`: reloads the panel in the open After Effects and
  checks it. See Checklists.
- `logs/commits.log` is written by a post-commit hook that amends each commit. This is normal.

## Status (2026-11-10)
Works, verified in After Effects 26.5 by reading rendered pixels and effect values:
- Analyzer on the 10 test looks: mean normalized error 0.150 (`score.py`).
- Panel v16: upload reference and footage (the reference is applied at once), per-part sliders
  with checkboxes, Strength, Lumetri grade, regions (hue, value, saturation, opacity, blend),
  auto masks (Vision subject/people; luma and color ranges), icons with tooltips, sections.
- Floating window (File > Scripts) scrolls on every tab with its own bar.
- `tools/panel_check.py`: 9 of 9 checks pass.

Open or unverified:
- **Docked panel (Window > Look Decomposer) shows no scroll bar** for the user. Code v16 gives
  docked panels the custom bar, capped to the panel height, but this was not seen in After
  Effects after a restart. ScriptUI cannot use After Effects' own scroll handle here.
- Uploads were tested through their functions with the same file paths. The file dialogs
  were not driven.
- Rectangle region shape and the region Saturation and Value sliders are not pixel-checked.
- A video gets one frame's look for the whole clip.
- Auto-mask regions add two layers (an adjustment layer and a matte layer). The panel names
  them and removes them.
- The floating window is about 356 px wide and not optimized.
- The bridge answered once with "ran the script but did not write a response". The next run
  worked. Cause unknown. First check the file-access setting (see below).

## Decisions and why
- Reference looks are applied to the raw footage, never to the already-graded still. Applying
  a look to its own graded image grades it twice. On the warm_sunset test the error against
  the reference was 19.3 (raw plate + look) vs 22.4 (graded still + look). The graded version
  is visibly over-saturated (colour spread 85 vs 64).
- Footage uploads are not analyzed for their own look, for the same reason.
- The panel refers to layers by string IDs stored in layer comments (`"id":...`), never by
  layer objects. Touching a deleted layer throws "Object is invalid", which try/catch cannot catch.
- ScriptUI quirks found the hard way: `layout.layout(true)` resets manual `location`
  changes; a palette's size is fixed when built (set caps before `show`); a docked panel's
  `size` setter is ignored (After Effects sizes it).
- Panel code is ES3 and ASCII-only. This After Effects has no `JSON`; the panel evals plain
  data.
- Hue/Saturation channel numbers, verified by pixels: 1 All, 2 Reds, 3 Yellows, 4 Greens,
  5 Cyans, 6 Blues, 7 Magentas.
- Scripts cannot turn on "Allow Scripts to Write Files and Access Network". After Effects
  refuses. The user must turn it on. Never edit After Effects preference files to get around it.

## Rules from the user
- Test in the user's real setup. The user uses the docked panel; I missed the docked cap bug
  by testing only the floating window.
- Don't claim something works without evidence. Screen capture is blocked on this Mac (no
  Screen Recording permission), so verify with numbers and say what was not seen.
- Don't commit or push unless asked. Ask before committing `test_stills/Auto-Save/` and
  `test_stills/ground_truth.aep`.
- Don't remove items from the user's After Effects project. Remove only items you created,
  by ID, after taking a snapshot. Don't save the After Effects project.
- Keep replies short, and do what was asked.

## Checklists
After changing the panel:
1. `python3 look_decomposer/tools/panel_check.py`. Needs After Effects open with the panel
   installed. It must print "9 of 9 checks passed".
2. For docked behavior, restart After Effects, then open Window > Look Decomposer. A docked
   panel does not reload on its own.
3. Stage only the intended paths. The post-commit hook amends the commit to add the log.

Driving After Effects from an agent: `look_decomposer/ae_transport.run_jsx(code)` or the
`aftereffects_run` tool. Close any test windows and remove the items you created.

## Secrets
Never write passwords, keys, or tokens into this file or any repo file.
`~/.config/opencode/service.json` contains a password. Do not read it or copy it.
`~/.config/opencode/opencode.jsonc` holds MCP settings; a review found no keys in it.

## Outside the repo
- `~/Library/Application Support/LookDecomposer/Mattes/`: auto-mask PNGs from today's tests.
  Ask before deleting.
- `~/Library/Preferences/Adobe/After Effects/26.0|26.5/Scripts/`: installed panel loaders.
- `~/Library/Application Support/AE-MCP-Bridge/`: bridge request and response files.

## Next steps
1. Restart After Effects, open Window > Look Decomposer, and check whether a scroll bar
   appears at the panel's right edge when the panel is shorter than its content. If it still
   doesn't, decide between a UXP panel (After Effects UXP public beta is planned for
   November 2026) and another layout.
2. Decide whether to commit `test_stills/ground_truth.aep` and the Auto-Save folder.
3. Analyzer work toward the Nov 17 milestone: glow intensity, exposure and gamma, and
   split-tone strength are the weakest fields in `test_stills/scores.json`.
