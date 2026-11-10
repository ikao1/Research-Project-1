#!/usr/bin/env python3
"""Minimal structural validator for look-decomposer analysis JSON.

Checks the parts the AE builder relies on (types and AE parameter ranges)
without external dependencies. Returns a list of error strings; empty = valid.
"""

import re

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

ASPECTS = {
    "exposure": {"stops": (-10, 10), "gamma": (0.001, 10)},
    "levels": {
        "input_black": (0, 0.98), "input_white": (0.02, 1), "gamma": (0.001, 10),
        "output_black": (0, 0.98), "output_white": (0.02, 1),
    },
    "white_balance": {"temperature": (-100, 100), "tint": (-100, 100)},
    "saturation": {"amount": (-100, 100)},
    "blur": {"radius_px": (0, 500)},
    "glow": {"threshold": (0, 255), "radius_px": (0, 500), "intensity": (0, 100)},
    "vignette": {
        "amount": (-5, 5), "midpoint": (0, 100),
        "roundness": (-100, 100), "feather": (0, 100),
    },
    "grain": {"amount": (0, 100)},
}

REQUIRED_ASPECT_FIELDS = {
    "split_tone": ("shadows_hex", "highlights_hex", "strength"),
    "exposure": ("stops",),
    "levels": (),
    "white_balance": (),
    "saturation": ("amount",),
    "blur": ("radius_px",),
    "glow": (),
    "vignette": ("amount",),
    "grain": ("amount",),
}

NOTE_TOPICS = set(ASPECTS) | {"general"}


def validate(analysis):
    errors = []

    if not isinstance(analysis, dict):
        return ["analysis must be a JSON object"]

    if analysis.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0' (got %r)" % analysis.get("schema_version"))

    if not isinstance(analysis.get("name"), str) or not analysis.get("name", "").strip():
        errors.append("name must be a non-empty string")

    source = analysis.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        if source.get("type") not in ("image", "video"):
            errors.append("source.type must be 'image' or 'video'")
        for dim in ("width", "height"):
            value = source.get(dim)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
                errors.append("source.%s must be a positive integer" % dim)

    look = analysis.get("look")
    if not isinstance(look, dict):
        errors.append("look must be an object")
        return errors

    for aspect, params in ASPECTS.items():
        section = look.get(aspect)
        if section is None:
            continue
        if not isinstance(section, dict):
            errors.append("look.%s must be an object" % aspect)
            continue
        for field, (low, high) in params.items():
            if field not in section:
                continue
            value = section[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append("look.%s.%s must be a number" % (aspect, field))
            elif not low <= value <= high:
                errors.append(
                    "look.%s.%s = %r outside AE range [%g, %g]" % (aspect, field, value, low, high)
                )
        conf = section.get("confidence")
        if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float))
                                 or not 0 <= conf <= 1):
            errors.append("look.%s.confidence must be 0..1" % aspect)
        for field in REQUIRED_ASPECT_FIELDS[aspect]:
            if field not in section:
                errors.append("look.%s.%s is required" % (aspect, field))

    split = look.get("split_tone")
    if isinstance(split, dict):
        for field in ("shadows_hex", "highlights_hex"):
            value = split.get(field)
            if not isinstance(value, str) or not HEX_RE.match(value):
                errors.append("look.split_tone.%s must be '#rrggbb'" % field)
        strength = split.get("strength")
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not 0 <= strength <= 100:
            errors.append("look.split_tone.strength must be 0..100")

    grain = look.get("grain")
    if isinstance(grain, dict) and "monochrome" in grain and not isinstance(grain["monochrome"], bool):
        errors.append("look.grain.monochrome must be a boolean")

    for unknown in set(look) - set(ASPECTS) - {"split_tone"}:
        errors.append("unknown look aspect: %r" % unknown)

    notes = analysis.get("notes")
    if notes is not None:
        if not isinstance(notes, list):
            errors.append("notes must be an array")
        else:
            for i, note in enumerate(notes):
                if not isinstance(note, dict) or not isinstance(note.get("message"), str):
                    errors.append("notes[%d] needs a message string" % i)
                elif note.get("topic") not in NOTE_TOPICS:
                    errors.append("notes[%d].topic %r is not a known topic" % (i, note.get("topic")))

    overall = analysis.get("overall_confidence")
    if overall is not None and (isinstance(overall, bool) or not isinstance(overall, (int, float))
                                or not 0 <= overall <= 1):
        errors.append("overall_confidence must be 0..1")

    return errors
