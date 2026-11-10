# Look Decomposer

Reverse-engineer a composited look from a reference image and rebuild it in
After Effects as an editable comp with named adjustment layers and live
sliders.

```
reference media → analyzer (Python/PIL) → analysis JSON → AE builder (ExtendScript)
                                                    ↘ generated how-to guide (Nov 17)
```

## Status

**Nov 10 milestone (technical spike) — complete.**

- `schema/analysis.schema.json` — the contract between analyzer and builder
  (see `docs/schema.md` for the human version).
- `ae/look_fx.jsx` — the AE engine: builds `LOOK — <name>` comps from an
  analysis JSON. Edit mode = named adjustment layers (`LOOK 01 — Exposure`,
  ...) plus a `LOOK CONTROLS` null with Slider Control effects wired by
  expressions; flat mode = the same effect stack applied directly to the
  source (used to render ground truth).
- `test_stills/` — deterministic base plate + 10 ground-truth looks
  (JSON + rendered PNG + `ground_truth.aep`). The parameter readback of every
  GEN comp was verified against its JSON: 0 mismatches.
- Since then (Nov 10): the After Effects panel (`ae_panel/`), auto masks (`automask.py`),
  the how-to guide (`guide.py`), and scoring (`score.py`, mean error 0.150). Open issues are
  listed in `AGENTS.md` at the project root.

## Layout

| Path | What |
|---|---|
| `look_decomposer/schema/analysis.schema.json` | machine-readable schema |
| `look_decomposer/validate.py` | dependency-free structural validator |
| `look_decomposer/ae/look_fx.jsx` | AE engine (LOOKFX.buildComp) |
| `look_decomposer/ae/build_look_comp.jsx` | Run Script File entry point |
| `look_decomposer/ae_transport.py` | sends JSX to live AE via the DoScript bridge |
| `look_decomposer/build.py` | CLI: build a comp from analysis JSON |
| `look_decomposer/analyzer.py` | estimates a look from an image (the core of the tool) |
| `look_decomposer/score.py` | scores predictions against the 10 test looks |
| `look_decomposer/guide.py` | how-to markdown from an analysis |
| `look_decomposer/automask.py` | auto masks: subject, people, tones, colors |
| `look_decomposer/install_panel.py` | installs the After Effects panel loader |
| `look_decomposer/ae_panel/LookDecomposer.jsx` | the After Effects panel |
| `look_decomposer/tools/panel_check.py` | reloads the panel in open AE and checks it |
| `look_decomposer/tools/make_icons.py` | draws the panel icons |
| `look_decomposer/tools/automask_vision.swift` | Apple Vision helper for subject and people masks |
| `look_decomposer/make_base_plate.py` | generates the neutral test plate |
| `look_decomposer/generate_test_stills.py` | renders ground-truth looks in AE |
| `test_stills/looks/*.json` | the 10 ground-truth looks |
| `test_stills/renders/*.png` | AE renders of those looks |
| `test_stills/ground_truth.aep` | AE project with the GEN comps |

## Usage

After Effects must be open (the ae_mcp DoScript bridge handles the rest).

```sh
# Build an editable comp from a look JSON
python3 -m look_decomposer.build test_stills/looks/noir.json

# Flat build with a PNG preview of the result
python3 -m look_decomposer.build test_stills/looks/noir.json --mode flat --export out.png

# Regenerate the base plate and all ground-truth stills
python3 -m look_decomposer.generate_test_stills --regenerate-plate
```

In the built comp, grab the `LOOK CONTROLS` layer and drag its slider effects
(`Exposure`, `Contrast`, `Temperature`, `Saturation`, ...) — every wired
parameter updates through expressions.

## The test set

`test_stills/looks/` holds ten looks covering the v1 aspect space: warm_sunset,
teal_orange, bleach_bypass, moody_blue, filmic_faded, soft_dreamy, high_key,
noir, vhs, natural_reference (near-neutral control for false positives).
Each pair `(renders/<slug>.png, looks/<slug>.json)` is the scored target for
the Nov 17 analyzer.

The base plate embeds calibration regions the analyzer will lean on: an
11-step gray ramp, a 24-patch color chart, a 12px checkerboard, and fine
3px stripes (blur estimation), plus a synthetic scene (sky gradient, sun,
mountains, water with sun-glitter path, foreground rocks).

## Effect mapping (verified on AE 26.5)

| Aspect | Effect | Notes |
|---|---|---|
| exposure | ADBE Exposure2 | master stops/gamma |
| levels | ADBE Pro Levels2 | contrast + matte fade |
| white_balance | ADBE Lumetri (Basic Correction) | temperature/tint ±100 |
| saturation | ADBE Color Balance (HLS) | Saturation accepts expressions; Hue/Saturation's does not |
| split_tone | ADBE Tint | Map Black/White To + Amount |
| blur | ADBE Gaussian Blur 2 | |
| glow | ADBE Glo2 | |
| vignette | ADBE Lumetri (Vignette) | amount -5..5 |
| grain | ADBE Noise2 | Noise Type 0=mono 1=color |

## Analyzer, guide, and scoring (Nov 17 MVP)

| Path | What |
|---|---|
| `look_decomposer/analyzer.py` | estimates an analysis JSON from a rendered image (`--reference` plate optional; without it, confidence is scaled down) |
| `look_decomposer/guide.py` | rule-based markdown how-to from an analysis JSON; each step quotes the analyzer's reason and confidence |
| `look_decomposer/score.py` | scores predictions against the 10 ground-truth looks; writes `test_stills/scores.json` |

```sh
python3 -m look_decomposer.analyzer test_stills/renders/warm_sunset.png \
    --reference test_stills/base_plate.png -o warm_sunset.analysis.json
python3 -m look_decomposer.build warm_sunset.analysis.json --no-open
python3 -m look_decomposer.guide warm_sunset.analysis.json -o warm_sunset.guide.md
python3 -m look_decomposer.score
```

Current score (reference mode, mean normalized error over the 10 looks): **0.150**.
Weakest fields: glow intensity, exposure stops/gamma, split-tone strength, saturation.
Split tone is only reported when the tone colors have at least 0.06 chroma; lower
values let luma-only curves masquerade as split toning.

## Use it inside After Effects (panel)

One-time setup:

1. Install Pillow for the Python you will use:
   `python3 -m pip install pillow`
2. Install the panel:
   `python3 -m look_decomposer.install_panel`
3. In After Effects, open Preferences > Scripting & Expressions and turn on
   **Allow Scripts to Write Files and Access Network**.
4. Restart After Effects.

Open the panel from **Window > Look Decomposer**. It docks like any other panel,
so you can drag its tab next to Project or Effects. File > Scripts > Open Look
Decomposer opens the same window as a floating palette.

The panel has four tabs:

1. **Upload.**
   - **A. Reference look**: upload a still or a video that has the look you want.
     It is analyzed (a video uses its middle frame). If footage is already the
     working footage, the look is applied to it at once.
   - **B. Footage to grade**: upload one or more pictures or videos. Each is added
     to the composition with the reference look applied, and the panel switches to
     tab 2 so the sliders are ready. Unsupported files are skipped and named.
2. **Adjust.** Strength, and one slider per part of the look (Brightness, Black
   point, White point, Faded blacks, Warm / cool, Tint, Color strength, Split tone,
   Softness, Glow, Dark corners, Film grain). Uncheck a box to turn that part off.
   **Apply reference look** resets the slider changes on the working footage.
   **Remove look** takes the look off and keeps the grade.
3. **Grade.** Lumetri Color controls on the working footage, applied after the
   look: Exposure, Contrast, Highlights, Shadows, Whites, Blacks, Saturation,
   Vibrance, Sharpen, and Mix (the grade's opacity). Works with or without a look.
4. **Regions.** Auto mask, then regions:
   - **Auto mask** selects an area of the working footage: Subject or People
     (Apple Vision), Highlights, Midtones, Shadows, or a Color range. Grow /
     shrink, edge softness, and invert adjust it. The region's hue, value, and blend
     settings then apply only inside the mask. A region made this way is an
     adjustment layer plus a matte layer, both created and named by the panel;
     **Remove region** deletes both.
   - **Add region** makes a hue/value/blend region without a mask. Colors picks the
     hue range; Area limits it to an ellipse or rectangle.

**Layout.** Controls are grouped under headings in each tab: Upload has the reference
look, the footage, and the setup check; Adjust has the look's strength and then Light,
Color, and Effects; Grade has Light, Color, and Finish; Regions has the region list,
then "1. Choose the area" (auto mask or a manual ellipse/rectangle), then "2. Change the
area" (colors, hue, value, saturation, opacity, blend).

**Icons and scrolling.** Each slider has an icon, and hovering over the icon or the
label shows what the slider does. Icons are drawn by `look_decomposer/tools/make_icons.py`
into `look_decomposer/ae_panel/icons/`. Each tab has a scroll bar on its right side, with
▲ and ▼ arrows above and below it (the arrows scroll 20 pixels; they dim at the ends of
the tab). Both the docked panel (Window > Look Decomposer) and the floating window (File > Scripts) use the bar
on the right of each tab. The docked panel's bar is sized to the panel's height; if you resize the panel and
the scroll range looks wrong, click another tab to refresh it. A bar that is greyed out has nothing to scroll.
ScriptUI cannot use After Effects' own scroll handle, and it did not appear for this panel, so the panel draws its own.
That bar moves the controls a pixel at a time, and a control that is only partly visible at the
top or bottom edge is hidden until it fits.

**Working footage** is the selected footage layer in the timeline. If nothing is
selected, it is the footage you uploaded or used last. The sliders need no
selection once footage is uploaded.

**Why footage is not analyzed.** The analyzer measures a look relative to the
neutral base plate. Applying that look to the same graded image grades it twice.
On the warm_sunset test, the reference look applied to the raw plate gave a mean
error of 19.3 against the reference render (raw footage: 24.4). The same look
applied to the already-graded render gave 22.4, with colour spread 85 against 64
for the reference, which is visibly over-saturated.

**Stored settings.** Each footage layer keeps its look, slider changes, grade and
strength in its layer comment, and each region keeps its settings in its comment.
Layers are found again by an ID stored there, so deleting a layer in After Effects
cannot break the panel.

Check the setup any time with `python3 -m look_decomposer.install_panel --status`.
If you move the project folder, run the installer again.

Tested on After Effects 26.5 (macOS), by reading rendered pixels and effect values:
- Solid layer or precomp selected for an auto mask: a plain message for a solid;
  precomp masks work.
- Auto mask with no selection, using the working footage.
- Upload of raw footage with the reference look applied; rendered result checked
  against the reference (see above).
- Subject mask on an uploaded photo with several people.
- Sliders with no reference (brightness and split tone create their effects),
  Strength (50% halves the value), Grade, Remove look, Reset grade.
- Video reference and video footage; multi-file upload with an unsupported file.
- Working footage deleted by hand: no error, and the panel says what to do.
- Region removal and the sliders afterward.

Not tested: the file dialogs themselves (the panel was driven through its functions
with the same file paths), the rectangle region shape, and per-frame video
analysis (a video uses one frame for the whole clip). Auto mask matte files are
kept in `~/Library/Application Support/LookDecomposer/Mattes`.
