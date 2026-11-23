# Research Project 1 — Look Decomposer

> Reverse-engineer a composited look from a reference image and rebuild it inside
> After Effects as an editable stack of named layers and live sliders.
>
> **[Demo video: `docs/demo.mp4`](docs/demo.mp4)** (75 s). It walks a reference
> through analyze → rebuild → verify. The rebuilt frames in it are rendered by
> the tool's own After Effects engine (`look_fx.jsx` flat mode); macOS screen
> capture is blocked on this machine, so this AE render is the recording of the
> tool's output. The panel itself is shown in class.

## What I set out to do

The proposal (`docs/proposal.md`) was a tool that takes a reference screenshot
or short video, **explains how its final look was built**, and **reconstructs
that look inside After Effects** as an editable composition — named adjustment
layers, adjustable effect sliders, and a generated how-to guide. The pipeline:

```
reference media → vision analysis (color, tonality, blur, grain, vignette,
segmentation) → analysis JSON → AE builder script → editable comp + generated guide
```

The plan was a three-week build: a technical spike by Nov 10 (AE script that
builds comps + a test set + the schema), a still-image MVP by Nov 17
(analyzer + builder + rule-based guide), and video + subject separation +
polish by Nov 23.

## What I made

Everything in the proposal's "smallest version that still counts" works, plus
the interactive panel that was the Nov 23 goal:

- **Analyzer** (`look_decomposer/analyzer.py`): estimates a look from an image —
  exposure, levels/contrast and fade, white balance, saturation, split toning,
  blur, glow, vignette, and grain — using the calibration regions of a neutral
  base plate (gray ramp, color chart, checkerboard, fine stripes), and writes
  the schema-compliant JSON (`docs/schema.md`, `look_decomposer/schema/`).
- **AE engine** (`look_decomposer/ae/look_fx.jsx`): builds a `LOOK — <name>`
  comp from the JSON — named adjustment layers per aspect, plus a `LOOK CONTROLS`
  null whose sliders drive the whole stack through expressions. Edit mode
  (layers + sliders) and flat mode (renders ground truth) were both verified:
  parameter readback of every GEN comp matches its JSON exactly.
- **After Effects panel** (`look_decomposer/ae_panel/LookDecomposer.jsx`): four
  tabs — Upload (reference look), Adjust (strength + one slider per part of the
  look), Grade (Lumetri), Regions (auto masks and hue/value/blend regions). A
  big "Use this composition" button starts the tool on the open comp. The panel
  stores each layer's look and grade in its layer comment and finds layers by
  ID, so deleting a layer can't break it. Each tab has its own scroll bar
  (ScriptUI has no scrollable groups, so the panel draws one and moves rows by
  hand). 9 of 9 automated checks pass (`tools/panel_check.py`).
- **Auto masks** (`look_decomposer/automask.py` + an Apple Vision helper): subject,
  people, highlights/midtones/shadows, and color-range masks applied as a
  matte to a region, so edits apply only inside the mask.
- **Generated guide** (`look_decomposer/guide.py`): a rule-based markdown
  how-to that quotes the analyzer's reasons and confidence per step.
- **Test set and scoring**: ten ground-truth looks rendered by After Effects
  itself (`test_stills/looks/` + `renders/`), scored by `score.py`. Current
  **mean normalized error: 0.150** (was 0.194 mid-project). The analyzer runs
  with and without the base plate; without it, confidence is scaled down
  honestly.
- **Bridge** (`ae_mcp/`): an MCP bridge that drives a live After Effects
  session over AppleScript DoScript — used to build, verify, and test
  everything against the real application.

### How the project changed, and why

1. **Split tone moved from Hue/Saturation to Color Balance (HLS).** AE's
   Hue/Saturation parameters cannot hold expressions, so the panel would have
   broken; the replacement is visually identical.
2. **Reference looks are applied to raw footage, never to an already-graded
   image.** Applying a look to its own graded image grades it twice: on the
   warm_sunset test the error was 19.3 (raw plate + look) vs 22.4 (graded
   still + look), visibly over-saturated (colour spread 85 vs 64).
3. **The panel is the deliverable, not just the builder script.** The proposal's
   "video + polish" week became the panel because that's what made the tool
   usable in After Effects. Video analysis remains a stretch goal (a video gets
   one frame's look today).
4. **The docked-panel scroll bar.** After Effects' own scroll handle does not
   appear for this panel, so the panel draws its own; the docked cap reads the
   real tab position.

## How to run it

**Prereqs:** After Effects (tested on 26.5), Python 3 with Pillow, the panel
installed, and **Preferences > Scripting & Expressions > Allow Scripts to Write
Files and Access Network** turned on in After Effects.

```sh
# One-time setup
python3 -m pip install pillow
python3 -m look_decomposer.install_panel        # installs the panel loaders
python3 -m look_decomposer.install_panel --status
```

Then restart After Effects and open **Window > Look Decomposer**.

**Use it (interactive):**

1. Tab 1 → **Upload reference look** (a still or video with the look to copy).
2. Open (or create) a composition with your footage and press the big
   **Use this composition** button: the look is applied to the footage at once.
3. Tab 2 → drag the sliders (Brightness, Warm/cool, Glow, Film grain, ...);
   uncheck a box to turn a part off; Strength scales the whole look.
4. Tab 3 → Lumetri grade on top of the look.
5. Tab 4 → Regions: auto mask (Subject, People, Highlights, Midtones, Shadows,
   Color range) and hue/value/blend changes limited to an area.

**Use it (command line, no panel):**

```sh
# Analyze a still against the base plate
python3 -m look_decomposer.analyzer test_stills/renders/warm_sunset.png \
    --reference test_stills/base_plate.png -o warm_sunset.analysis.json
# Build an editable comp from the JSON
python3 -m look_decomposer.build warm_sunset.analysis.json
# Generate the how-to guide
python3 -m look_decomposer.guide warm_sunset.analysis.json -o warm_sunset.guide.md
# Score the analyzer against the 10 ground-truth looks
python3 -m look_decomposer.score
# Check the installed panel in the open After Effects
python3 look_decomposer/tools/panel_check.py
```

## What I learned

- **Inverting a composite is underdetermined**, exactly as the proposal's
  riskiest-part predicted. The same flattened picture can come from different
  stacks, so every estimate must be an *editable starting point*, not a
  guarantee. The schema, the notes, and the confidence numbers encode that
  honesty; the guide quotes them.
- **Test against ground truth you trust.** Rendering the 10 looks with After
  Effects itself (flat mode, then reading every parameter back) gave the
  scoring something real to measure against, and caught effect quirks (Noise
  Type defaults to color noise; Hue/Saturation rejects expressions) that docs
  don't mention.
- **AE scripting has sharp edges.** ScriptUI cannot scroll groups or clip
  children, a docked panel's size is set by AE, `layout(true)` resets manual
  positions, removed layers throw uncatchable "Object is invalid" errors — the
  panel works around all of these (ID-in-comment layer tracking, hand-placed
  rows, careful measurement).
- **Measure, don't eyeball.** Screen capture is blocked on this Mac, so every
  claim was verified with numbers (pixel reads, parameter readback, panel
  checks) and what was not seen was said so.

## What doesn't work yet

- **Video** gets one frame's look for the whole clip — no temporal analysis.
- **Weakest analyzer fields**: glow intensity (0.478 mean error), exposure
  stops (0.324) and gamma (0.300), split-tone strength (0.240) — see
  `test_stills/scores.json`.
- The **docked panel's scroll bar** was not seen in After Effects after a
  restart (floating window verified); ScriptUI cannot use AE's own handle.
- The **file dialogs** were tested through the same functions with the same
  paths, not by driving the dialogs themselves.
- Subject masks work on photos; the People mode misses illustrated characters.

## What I'd do next

1. Improve the three weak fields (glow, exposure/gamma, split-tone strength)
   with better gates and region-wise estimates.
2. Temporal analysis for video: sample frames, fit per-clip look with
   keyframed sliders.
3. Fix or replace the docked-panel scrolling (UXP panel when AE's UXP beta
   lands).
4. Output the tutorial-style guide as keyframed steps in the comp, not just
   markdown.

## Repo layout

| Path | Purpose |
| --- | --- |
| `docs/` | proposal, schema, research log, demo notes, this video's script |
| `ae_mcp/` | MCP bridge that drives a live After Effects session |
| `look_decomposer/` | analyzer, AE engine, panel, guide, scoring, auto masks |
| `test_stills/` | base plate, 10 ground-truth looks, renders, scores |
| `AGENTS.md` | working notes for coding agents: status, decisions, rules |

Full commit history tells the build story; every commit carries a real message
(`logs/commits.log`).
