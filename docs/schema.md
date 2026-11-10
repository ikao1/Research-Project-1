# Look Decomposer — Analysis Schema (v1)

The analysis JSON is the contract between the three halves of the tool:

```
analyzer (Python vision)  →  analysis JSON  →  AE builder (ExtendScript)
```

An **absent look section means "not detected / neutral"** — the builder will not
create a layer for it. Every numeric range below is the range of the After
Effects parameter it drives, so values can be pushed into AE without
conversion. Full machine-readable schema:
[`look_decomposer/schema/analysis.schema.json`](../look_decomposer/schema/analysis.schema.json)

## Top level

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `"1.x"` | Bump the minor when adding optional fields. |
| `name` | string | Slug used in comp names (`LOOK — noir`). |
| `source` | object | `path` (relative paths resolve against the JSON file), `type` (`image`/`video`), `width`, `height`, `frames`. |
| `look` | object | See aspects below. |
| `notes` | array | `topic` + `message` + optional `confidence`; the rule-based "why" behind each estimate. Feeds the generated how-to guide. |
| `overall_confidence` | 0..1 | Honest summary of how sure the analyzer is. |

## Look aspects (applied bottom → top in this order)

Each aspect maps to one **named adjustment layer** in the built comp, and each
carries an optional `confidence` (0..1).

| # | Aspect | AE effect | Parameters (ranges) |
|---|---|---|---|
| 1 | `exposure` | Exposure | `stops` (-10..10), `gamma` (0..10) |
| 2 | `levels` | Levels (Individual Controls) | `input_black` (0..0.98), `input_white` (0.02..1), `gamma`, `output_black`, `output_white` — contrast + matte fade |
| 3 | `white_balance` | Lumetri Color | `temperature` (-100..100), `tint` (-100..100) |
| 4 | `saturation` | Color Balance (HLS) | `amount` (-100..100) — uses Color Balance (HLS)'s Saturation, which behaves like Hue/Saturation's Master Saturation but accepts expressions |
| 5 | `split_tone` | Tint | `shadows_hex`, `highlights_hex` (`#rrggbb`), `strength` (0..100) |
| 6 | `blur` | Gaussian Blur | `radius_px` (0..500) |
| 7 | `glow` | Glow | `threshold` (0..255), `radius_px`, `intensity` (0..100) |
| 8 | `vignette` | Lumetri Color (Vignette) | `amount` (-5..5), `midpoint` (0..100), `roundness` (-100..100), `feather` (0..100) |
| 9 | `grain` | Noise | `amount` (0..100), `monochrome` (bool) |

## Slider controls

In `edit` mode the builder also creates a **`LOOK CONTROLS`** null layer with
named *Slider Control* effects (`Exposure`, `Contrast`, `Fade Lift`,
`Temperature`, `Tint`, `Saturation`, `Split Tone Strength`, `Blur`,
`Glow Intensity`, `Vignette Amount`, `Grain`). Each slider is wired to the
matching effect parameter with an expression, so the whole look can be steered
from one place without opening the Effect Controls panel.

## Known approximations (v1)

- **Split tone** uses AE's *Tint* (map black→shadows color, white→highlights
  color). Partial `strength` blends back toward the original, but Tint's blend
  is luma-based, so strong settings desaturate — same behavior as most
  "duotone" recipes, documented rather than hidden.
- **Levels gamma** has no master slider (advanced; tweak it on the Levels
  effect directly).
- Asymmetric contrast/fade is supported in the JSON but the `Contrast` /
  `Fade Lift` sliders assume symmetric values; the builder warns and keeps the
  remainder on the effect itself.
- **Grain** is stochastic: two renders of the same look differ in noise, so
  reference/rebuild comparisons must tolerate that (compare with grain
  disabled, or statistically).
