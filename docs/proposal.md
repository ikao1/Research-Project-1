# Research Project 1 — Proposal

**Working title:** *Look Decomposer* — an After Effects re-compositing tool
**Software:** Adobe After Effects + a Python/vision analysis backend

## The project in one sentence

I'll build a tool that takes a reference screenshot or short video, explains how its final look was built, and reconstructs that look inside After Effects as an editable composition — named layers, adjustable effect sliders, and a generated how-to guide (with a video tutorial as a stretch goal).

## Why this one

This is the project that teaches me the most because it forces me to work in three places at once:

- **Reverse-engineer compositing.** To rebuild a look I have to understand color science, tonality/curves, white balance, grain, blur and depth of field, vignetting, light direction, and blend behavior — not just apply presets.
- **Build a real cross-software pipeline.** Python/vision analysis → a structured intermediate format → After Effects scripting (ExtendScript + ScriptUI). That's automation and tool-building, not a single comp.
- **Design usable tooling.** I have to turn fuzzy visual judgement into a parameter schema and sliders a human can actually tweak.

Afterward I'll be able to automate AE layer and effect creation, justify a grade numerically instead of by eye, and turn any reference into a reusable, adjustable template.

## What I'll show

Both a **tool** and a **piece of work**:

- An After Effects panel/script that reads an analysis file and builds a comp with editable adjustment layers and live sliders (curves, color, blur, grain, vignette, etc.).
- A generated **written how-to guide** explaining each inferred decision (stretch: a narrated/screen-recorded tutorial).
- **Side-by-side demos**: reference vs. rebuilt comp, on stills and a short video, with sliders adjusted live.

## How it works

`reference image/video → vision analysis (color, tonality, blur map, grain, vignette, subject segmentation) → analysis JSON → AE builder script → editable comp + generated guide`

## The three weeks

- **By Nov 10 — Technical spike.** Proposal in repo, test set of ~10 reference stills, and a working AE script that programmatically creates a comp with named adjustment layers and slider controls. Define the analysis schema.
- **By Nov 17 — Still-image MVP.** Python analyzer extracts global color/tone, contrast curve, saturation, grain, blur, and vignette and writes JSON. AE builder turns that JSON into an editable comp with sliders. Rule-based written how-to generated. Works on stills only.
- **By Nov 23 — Video + polish.** Sample frames from short video and analyze temporally; add subject/background separation via segmentation or matting; generate tutorial-style steps; package it in a panel/UI; document usage and limits.
- **Nov 24 — Final demo.** Live run on unseen images and video, side-by-side comparison, slider tweaks, and a clear statement of what the tool can and cannot infer.

## The smallest version that still counts

Analyzer reads **one image**, estimates **global color grade, contrast, vignette, grain, and blur**, and writes JSON. The AE script builds a comp with **adjustment layers and sliders** for each of those, plus a short written guide. Even with no subject-aware segmentation and no video, this is a working look-transfer tool with editable, adjustable layers — not a flattened result.

## The riskiest part

**Inverting a composite is underdetermined.** A flattened image does not uniquely encode which layers, blend modes, and parameters produced it, so the tool will sometimes be confidently wrong. The second risk is the bridge itself — keeping the AE panel, the analysis backend, and slider updates stable across versions. I'll de-risk both by starting with a **file-based JSON handoff and a fixed, well-defined schema**, treating the decomposition as an *estimate with editable sliders* rather than a guaranteed recovery, and keeping a manual fallback path for any layer the analyzer can't infer.

## Success criteria

- Any still image can be loaded and rebuilt as an adjustable comp in under a minute.
- Each inferred parameter is visible and tweakable without touching code.
- The generated guide explains *why* each value was chosen.
- Honest documentation of failure cases (e.g., heavy stylistic grading, complex multi-source comps).
