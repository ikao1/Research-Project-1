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

## Layout

| Path | What |
|---|---|
| `look_decomposer/schema/analysis.schema.json` | machine-readable schema |
| `look_decomposer/validate.py` | dependency-free structural validator |
| `look_decomposer/ae/look_fx.jsx` | AE engine (LOOKFX.buildComp) |
| `look_decomposer/ae/build_look_comp.jsx` | Run Script File entry point |
| `look_decomposer/ae_transport.py` | sends JSX to live AE via the DoScript bridge |
| `look_decomposer/build.py` | CLI: build a comp from analysis JSON |
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

## Next (Nov 17)

- `analyzer.py`: estimate exposure/levels/white-balance/saturation from the
  calibration regions + scene statistics; vignette/blur/grain/glow estimates
  from radial and frequency analysis.
- Guide generator: rule-based `notes` → markdown how-to.
- Scoring: predicted JSON vs. ground truth across the 10 looks.
