#!/usr/bin/env python3
"""Estimate a look-decomposer analysis JSON from a rendered image.

Sequential inversion of the AE effect stack. The builder applies
exposure -> levels -> white balance -> saturation -> split tone ->
blur -> glow -> vignette -> grain, so the analyzer runs the reverse:
grain, blur, then a joint exposure+levels+vignette+glow fit of the
luminance quantile curve (vignette anchored by the radial corner/center
ratio), then white balance and saturation refine against the fit and
the fit is re-run, and finally split tone is solved jointly from
dark/mid/bright region drifts. Every step corrects for the effects
already estimated, using per-effect response curves measured on real
After Effects renders (see calibrate.py).

Usage:
    python3 -m look_decomposer.analyze <image> [--reference plate.png]
                                       [--name slug] [-o analysis.json]
"""

import argparse
import json
import math
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from look_decomposer.stats import Frame, invert_curve
    from look_decomposer import validate
else:
    from .stats import Frame, invert_curve
    from . import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
CALIBRATION_JSON = Path(__file__).resolve().parent / "calibration.json"
DEFAULT_PLATE = REPO_ROOT / "test_stills" / "base_plate.png"

EMIT = {
    "exposure_stops": 0.12,
    "gamma": 0.08,
    "temperature": 5.0,
    "tint": 4.0,
    "saturation": 5.0,
    "in_black": 0.015,
    "in_white": 0.985,
    "out_black": 0.012,
    "out_white": 0.988,
    "vignette": 0.25,
    "blur": 1.5,
    "grain": 4.0,
    "glow": 0.12,
    "split_strength": 8.0,
    "split_drift": 0.02,
    "split_chroma": 0.06,
}

CONFIDENCE_SCALE_STANDALONE = 0.6

# Glow threshold used by the calibration sweep (ADBE Glo2 threshold 180/255).
GLOW_THRESH = 180 / 255.0

REGION_KEYS = {"dark": "dark_color", "mid": "mid_color", "bright": "bright_color"}
REGION_BANDS = {"dark": (0.0, 0.12), "mid": (0.30, 0.70), "bright": (0.85, 1.01)}


def load_calibration():
    return json.loads(CALIBRATION_JSON.read_text(encoding="utf-8"))


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _luma01(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _invert_decreasing(xs, ys, y):
    env = list(ys)
    for i in range(len(env) - 2, -1, -1):
        if env[i] < env[i + 1]:
            env[i] = env[i + 1]
    return invert_curve(xs, env, y)


def _interp(rows, value, key):
    """Interpolate a sweep metric at `value` (scalar or per-channel list)."""
    vals = rows["values"]
    if value <= vals[0]:
        return rows[key][0]
    if value >= vals[-1]:
        return rows[key][-1]
    for i in range(len(vals) - 1):
        if vals[i] <= value <= vals[i + 1]:
            t = (value - vals[i]) / (vals[i + 1] - vals[i])
            a, b = rows[key][i], rows[key][i + 1]
            if isinstance(a, list):
                return [a[j] + t * (b[j] - a[j]) for j in range(len(a))]
            return a + t * (b - a)
    return rows[key][-1]


def _region_response(cal, sweep_key, value, region):
    """Per-channel color response of a region vs the plate at `value`."""
    rows = cal[sweep_key]
    rkey = REGION_KEYS[region]
    cur = _interp(rows, value, rkey)
    return [cur[i] / max(1e-6, cal["plate"][rkey][i]) for i in range(3)]


def _quantile_gains(cal, sweep_key, value, quantiles):
    """Per-quantile luma gain of a sweep at `value`, relative to the plate."""
    rows = cal[sweep_key]
    pq = cal["plate"]["quantiles"]
    if value is None:
        return [1.0] * len(quantiles)
    zero = rows["values"][0]
    if zero == 0 or abs(value) < 1e-9:
        return [1.0] * len(quantiles)
    q = _interp(rows, value, "quantiles")
    return [q[i] / max(1e-6, pq[i]) for i in range(len(quantiles))]


def _levels_map(x, ib, iw, ob, ow):
    u = (x - ib) / max(1e-6, iw - ib)
    u = max(0.0, min(1.0, u))
    return ob + (ow - ob) * u


def _levels_inv(y, ib, iw, ob, ow):
    u = (y - ob) / max(1e-6, ow - ob)
    u = max(0.0, min(1.0, u))
    return ib + (iw - ib) * u


def _s_inv(y, sa, sb):
    if sb <= 1e-6:
        return y
    return (y - sa) / sb


class ToneFit(object):
    """Joint exposure + levels + vignette + glow fit.

    predicted quantile = C(t) * vg(t) * gg(t) * L((g(s) * q_ref(t))^gamma)
    where C composes the per-quantile gains of effects estimated before
    the fit (white balance, saturation) and vg/gg are the vignette/glow
    gains, searched as fit dimensions so bloom and corner falloff are not
    absorbed into exposure/levels. Loss = weighted quantile residuals +
    band masses (clip spikes, fades) + the radial corner/center ratio,
    which anchors vignette independently of the histogram. The reference
    histogram is pre-flattened into a CDF so band-mass terms are O(1).
    """

    def __init__(self, q_ref, q_out, C, ref, band_meas, tail_weight,
                 radial_target, vig_gains, glo_gains, vig_radial, glo_radial,
                 radial_pair=None, split_map=None, q_t=None):
        self.q_ref = q_ref
        self.q_out = q_out
        self.C = C
        # quantile levels (fractions) matching q_ref/q_out indices
        self.q_t = q_t
        hist = ref._histogram()
        self.total = float(sum(hist)) or 1.0
        cum = [0] * 257
        for i in range(256):
            cum[i + 1] = cum[i] + hist[i]
        self.cum = cum
        self.band_top, self.band_clip, self.band_bottom = band_meas
        self.w = tail_weight
        self.radial_target = radial_target
        self.vig_gains = vig_gains
        self.glo_gains = glo_gains
        self.vig_radial = vig_radial
        self.glo_radial = glo_radial
        outer, inner = radial_pair if radial_pair else (0.4, 0.65)
        self.r_outer = outer
        self.r_inner = inner
        self.r_inv = inner / max(1e-6, outer)
        # split tone acts on luma as an extra linear map applied after
        # levels: S(x) = sa + sb * x (gray-pixel approximation of
        # y = (1-k) x + k * lerp(cw, cb, x))
        self.sa, self.sb = split_map if split_map else (0.0, 1.0)

    def _above(self, q):
        i = int(math.ceil(q * 255 - 1e-9))
        i = max(0, min(256, i))
        return (self.total - self.cum[i]) / self.total

    def _below(self, q):
        i = int(math.ceil(q * 255 - 1e-9))
        i = max(0, min(256, i))
        return self.cum[i] / self.total

    def search(self, g_curve, vig_amounts, glo_amounts):
        stops_grid = [x * 0.2 for x in range(-6, 7)]
        best = self._grid(
            stops_grid, [1.0],
            [0.0, 0.04, 0.08, 0.12], [0.88, 0.92, 0.96, 1.0],
            [0.0, 0.03, 0.06, 0.09], [0.88, 0.92, 0.96, 1.0],
            g_curve, vig_amounts, glo_amounts)
        # gamma refinement if midtones suggest a curve
        for gamma in (0.75, 0.8, 0.85, 0.9, 0.95, 1.05, 1.1, 1.2, 1.3):
            cand = self._grid([best[0]], [gamma], [best[2]], [best[3]],
                              [best[4]], [best[5]], g_curve,
                              [best[6]], [best[7]])
            if cand[8] < best[8] * 0.95:
                fine = self._grid(
                    [x * 0.05 + best[0] for x in range(-4, 5)],
                    [gamma], [best[2]], [best[3]],
                    [best[4]], [best[5]], g_curve, [best[6]], [best[7]])
                if fine[8] < cand[8]:
                    best = fine
                else:
                    best = cand
                break
        for step in (0.05, 0.02, 0.01):
            b = best
            s0 = [max(-1.5, min(1.5, b[0] + d * step)) for d in (-2, -1, 0, 1, 2)]
            i0 = [max(0.0, min(0.16, b[2] + d * step * 2)) for d in (-2, -1, 0, 1, 2)]
            w0 = [max(0.8, min(1.0, b[3] + d * step * 2)) for d in (-2, -1, 0, 1, 2)]
            o0 = [max(0.0, min(0.12, b[4] + d * step * 2)) for d in (-2, -1, 0, 1, 2)]
            v0 = [max(0.8, min(1.0, b[5] + d * step * 2)) for d in (-2, -1, 0, 1, 2)]
            cand = self._grid(s0, [b[1]], i0, w0, o0, v0, g_curve,
                              [b[6]], [b[7]])
            if cand[8] < best[8]:
                best = cand
        # vignette + glow local refinement (levels/stops held fixed)
        for step in (0.25, 0.1):
            b = best
            vg0 = [max(-3.0, min(3.0, b[6] + d * step)) for d in (-2, -1, 0, 1, 2)]
            gg0 = [max(0.0, min(1.5, b[7] + d * step)) for d in (-2, -1, 0, 1, 2)]
            cand = self._grid([b[0]], [b[1]], [b[2]], [b[3]], [b[4]], [b[5]],
                              g_curve, vg0, gg0)
            if cand[8] < best[8]:
                best = cand
        return best

    def _grid(self, stops_grid, gammas, ibs, iws, obs, ows, g_curve,
              vig_amounts, glo_amounts):
        best = None
        n = len(self.q_ref)
        q_t = self.q_t
        sa, sb = self.sa, self.sb
        bf_plate = max(self._above(GLOW_THRESH), 0.02)
        for vig_a in vig_amounts:
            vg = self.vig_gains(vig_a)
            rv = self.vig_radial(vig_a)
            for glo_a in glo_amounts:
                gg = self.glo_gains(glo_a)
                gr = self.glo_radial(glo_a)
                cvg = [self.C[j] * vg[j] for j in range(n)]
                rvg = rv * gr
                c_hi = sum(cvg[9:]) / 4.0
                c_lo = sum(cvg[:4]) / 4.0
                for stops in stops_grid:
                    g = _interp(g_curve, stops, "mean_ratio")
                    if abs(stops) < 1e-9:
                        g = 1.0
                    for gamma in gammas:
                        xq = [(g * q) ** gamma for q in self.q_ref]
                        inv_g = 1.0 / max(1e-6, g)
                        inv_gamma = 1.0 / max(1e-6, gamma)
                        x_o = (g * self.r_outer) ** gamma
                        x_i = (g * self.r_inner) ** gamma
                        for ib in ibs:
                            for iw in iws:
                                if iw - ib < 0.05:
                                    continue
                                span = iw - ib
                                for ob in obs:
                                    for ow in ows:
                                        oscale = ow - ob
                                        uo = (x_o - ib) / span
                                        uo = 0.0 if uo < 0.0 else (1.0 if uo > 1.0 else uo)
                                        ui = (x_i - ib) / span
                                        ui = 0.0 if ui < 0.0 else (1.0 if ui > 1.0 else ui)
                                        mo = ob + oscale * uo
                                        mi = ob + oscale * ui
                                        rel = (mo / max(1e-6, mi)) * self.r_inv
                                        total = 3.0 * (rvg * rel
                                                       - self.radial_target) ** 2
                                        # pre-glow quantiles (8-bit clamped,
                                        # like the real per-effect chain)
                                        pre = [0.0] * n
                                        for j in range(n):
                                            u = (xq[j] - ib) / span
                                            if u < 0.0:
                                                u = 0.0
                                            elif u > 1.0:
                                                u = 1.0
                                            v = cvg[j] * (sa + sb * (ob + oscale * u))
                                            if v > 0.996:
                                                v = 0.996
                                            elif v < 0.0:
                                                v = 0.0
                                            pre[j] = v
                                        # glow bloom scales with how much of
                                        # the frame sits above the threshold;
                                        # the calibrated gains assume the
                                        # plate's pre-glow histogram
                                        bf = 0.0
                                        for j in range(1, n):
                                            if pre[j] >= GLOW_THRESH:
                                                lo = pre[j - 1]
                                                if lo >= GLOW_THRESH:
                                                    bf = 1.0 - q_t[j - 1]
                                                    break
                                                frac = ((GLOW_THRESH - lo)
                                                        / max(1e-9, pre[j] - lo))
                                                bf = 1.0 - (q_t[j - 1]
                                                            + frac * (q_t[j] - q_t[j - 1]))
                                                break
                                        if pre[0] >= GLOW_THRESH:
                                            bf = 1.0
                                        bloom = min(3.0, bf / bf_plate)
                                        for j in range(n):
                                            v = pre[j] * (1.0 + (gg[j] - 1.0) * bloom)
                                            if v > 0.996:
                                                v = 0.996
                                            d = v - self.q_out[j]
                                            total += self.w[j] * d * d
                                        # band masses pin the fades and clips
                                        q_top = _clamp((_levels_inv(
                                            _s_inv(0.90 / c_hi, sa, sb),
                                            ib, iw, ob, ow) * inv_g)
                                            ** inv_gamma, 0.0, 1.0)
                                        q_clip = _clamp((_levels_inv(
                                            _s_inv(0.98 / c_hi, sa, sb),
                                            ib, iw, ob, ow) * inv_g)
                                            ** inv_gamma, 0.0, 1.0)
                                        q_bot = _clamp((_levels_inv(
                                            _s_inv(0.02 / c_lo, sa, sb),
                                            ib, iw, ob, ow) * inv_g)
                                            ** inv_gamma, 0.0, 1.0)
                                        d_top = self._above(q_top) - self.band_top
                                        d_clip = (self._above(q_clip)
                                                  - self.band_clip)
                                        d_bot = (self._below(q_bot)
                                                 - self.band_bottom)
                                        total += 3.0 * (d_top * d_top
                                                        + d_clip * d_clip
                                                        + d_bot * d_bot)
                                        if best is None or total < best[8]:
                                            best = (stops, gamma, ib, iw, ob, ow,
                                                    vig_a, glo_a, total)
        return best


def _solve_split(regions):
    """Joint least-squares for Tint strength k and the two tone colors.

    For each candidate k the region equations are linear in the tone
    colors: drift_r = k * (m(l_r) - x_r) with m(l) = c_b + (c_w - c_b) l.
    Nine equations (3 regions x 3 channels), six color unknowns.
    """
    best = None
    for ki in range(1, 41):
        k = ki * 0.025
        if k < 0.05:
            continue
        A, bvec = [], []
        for label in ("dark", "mid", "bright"):
            x, y = regions[label]
            lr = _luma01(x)
            for c in range(3):
                rhs = (y[c] - x[c]) / k + x[c]
                row = [0.0] * 6
                row[c] = 1.0 - lr
                row[3 + c] = lr
                A.append(row)
                bvec.append(rhs)
        M = [[sum(A[r][i] * A[r][j] for r in range(len(A))) for j in range(6)] +
             [sum(A[r][i] * bvec[r] for r in range(len(A)))] for i in range(6)]
        for col in range(6):
            piv = max(range(col, 6), key=lambda r: abs(M[r][col]))
            M[col], M[piv] = M[piv], M[col]
            if abs(M[col][col]) < 1e-12:
                continue
            for r in range(6):
                if r != col:
                    fac = M[r][col] / M[col][col]
                    for cc in range(col, 7):
                        M[r][cc] -= fac * M[col][cc]
        sol = [M[i][6] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0
               for i in range(6)]
        resid = sum((sum(A[r][i] * sol[i] for i in range(6)) - bvec[r]) ** 2
                    for r in range(len(A)))
        if best is None or resid < best[0]:
            best = (resid, k, sol)
    return best


def analyze(image_path, reference_path=None, name=None, calibration=None):
    cal = calibration or load_calibration()
    plate_stats = cal["plate"]
    quantiles = cal["quantiles"]
    frame = Frame(image_path)
    ref = Frame(reference_path) if reference_path else Frame(DEFAULT_PLATE)
    has_ref = reference_path is not None

    slug = name or Path(image_path).stem
    look = {}
    notes = []
    pending_notes = []

    def note(topic, message, confidence):
        # message may be a zero-arg callable; it is evaluated after all
        # refinement passes so quoted numbers match the emitted look
        pending_notes.append((topic, message, confidence))

    base_conf = 1.0 if has_ref else CONFIDENCE_SCALE_STANDALONE

    detail_idx = plate_stats["hf_detail_indices"]
    base_hf = ref.detail_hf(detail_idx)
    base_radial = ref.radial_ratio()
    q_ref = [ref.quantile(t) for t in quantiles]
    q_out = [frame.quantile(t) for t in quantiles]

    # ------------------------------------------------------------------ grain
    sigma = frame.noise_std()
    sigma_chroma = frame.chroma_noise_std()
    amount_mono = invert_curve(cal["noise_mono"]["values"],
                               cal["noise_mono"]["noise_std"], sigma)
    amount_color = invert_curve(cal["noise_color"]["values"],
                                cal["noise_color"]["noise_std"], sigma)
    colorish = sigma_chroma > max(0.008, 0.35 * sigma)
    if colorish:
        grain_amount, grain_key = amount_color, "noise_color"
        monochrome = False
    else:
        grain_amount, grain_key = amount_mono, "noise_mono"
        monochrome = True
    grain_section = None
    if grain_amount >= EMIT["grain"]:
        grain_section = {"amount": round(grain_amount, 1),
                         "monochrome": monochrome}
        look["grain"] = grain_section
        note("grain",
             "Adjacent-pixel noise measured %.3f (color noise %s); inverting "
             "the AE Noise calibration curve gives amount %.0f%s. Grain is "
             "stochastic, expect a few units of slack."
             % (sigma, "detected" if colorish else "not detected",
                grain_amount, ", monochrome" if monochrome else ", color"),
             0.65 * base_conf)

    # ------------------------------------------------------------------- blur
    hf_img = frame.detail_hf(detail_idx)
    hf_ratio = hf_img / max(1e-6, base_hf)
    if grain_section is not None:
        noise_hf = cal[grain_key]["hf_ratio"]
        noise_vals = cal[grain_key]["values"]
        idx = min(range(len(noise_vals)),
                  key=lambda i: abs(noise_vals[i] - grain_amount))
        hf_ratio = max(0.0, hf_ratio - (noise_hf[idx] - 1.0))
    blur_radius = _invert_decreasing(cal["blur"]["values"],
                                      cal["blur"]["hf_ratio"], hf_ratio)
    if blur_radius >= EMIT["blur"]:
        look["blur"] = {"radius_px": round(blur_radius, 1)}
        note("blur",
             "High-frequency energy in detail regions is %.0f%% of the "
             "reference%s; the Gaussian Blur calibration curve maps that to "
             "a %.1f px radius. Blur under ~1.5 px is below what the metric "
             "resolves, so small radii are not reported."
             % (hf_ratio * 100,
                " (grain contribution removed)" if grain_section else "",
                blur_radius),
             0.5 * base_conf)

    # -------------------------------------------------------------- vignette
    # Radial corner/center ratio gives a prior for the vignette amount; it
    # is biased by grain clipping, levels crush and glow bloom, so the
    # joint tone fit below searches vignette as a dimension around this
    # prior (the radial ratio is also a fit loss term).
    radial_response = frame.radial_ratio() / base_radial
    plate_radial = plate_stats["radial_ratio"]
    vig_norm = [v / plate_radial for v in cal["vignette"]["radial_ratio"]]
    vignette_prior = invert_curve(cal["vignette"]["values"], vig_norm,
                                  radial_response)

    def vig_radial_fn(amount):
        if abs(amount) < 1e-9:
            return 1.0
        return _interp(cal["vignette"], amount, "radial_ratio") / plate_radial

    def glo_radial_fn(amount):
        if amount < 1e-9:
            return 1.0
        return _interp(cal["glow"], amount, "radial_ratio") / plate_radial

    # ------------------------------------------- saturation + WB (pass 1)
    mid_img = frame.masked_region_color(ref, *REGION_BANDS["mid"])
    mid_ref = ref.region_color(*REGION_BANDS["mid"])
    mid_chroma_img = frame.masked_region_chroma(ref, *REGION_BANDS["mid"])
    mid_chroma_ref = ref.region_chroma(*REGION_BANDS["mid"])

    def sat_estimate(wb_temp, wb_tint, chroma_scale=1.0, measured=None):
        if mid_chroma_ref <= 1e-6:
            return 0.0, 1.0
        chroma_img = mid_chroma_img if measured is None else measured
        ratio = chroma_img / mid_chroma_ref
        for sweep, val in (("temperature", wb_temp), ("tint", wb_tint)):
            if val:
                r = _interp(cal[sweep], val, "mid_chroma_ratio")
                if r > 0:
                    ratio /= r
        if abs(chroma_scale - 1.0) > 1e-6 and chroma_scale > 1e-6:
            ratio /= chroma_scale
        amount = invert_curve(cal["saturation"]["values"],
                              cal["saturation"]["mid_chroma_ratio"], ratio)
        factor = _interp(cal["saturation"], amount, "mid_chroma_ratio")
        return amount, factor

    def wb_match(sat_factor):
        if mid_img is None or mid_ref is None:
            return 0, 0
        if sat_factor is not None and sat_factor < 0.35:
            # saturation near -100 destroys the channel-ratio information
            # white balance needs; report neutral rather than amplified noise
            return 0, 0
        l = _luma01([v / 255.0 for v in mid_ref])
        measured = []
        for c in range(3):
            img_c = mid_img[c] / 255.0
            ref_c = mid_ref[c] / 255.0
            if sat_factor and abs(sat_factor - 1.0) > 1e-6:
                img_c = l + (img_c - l) / sat_factor
            measured.append(img_c / max(1e-6, ref_c))
        scale = sum(measured) / 3.0
        norm = [m / max(1e-6, scale) for m in measured]

        def dist_at(temp, tint_):
            pred = [a * b for a, b in zip(
                _region_response(cal, "temperature", temp, "mid"),
                _region_response(cal, "tint", tint_, "mid"))]
            pscale = sum(pred) / 3.0
            pnorm = [p / max(1e-6, pscale) for p in pred]
            return sum((math.log(max(1e-6, norm[c]) /
                                 max(1e-6, pnorm[c]))) ** 2
                       for c in (0, 2))

        best = (1e18, 0, 0)
        for temp in cal["temperature"]["values"]:
            for tint_ in cal["tint"]["values"]:
                d = dist_at(temp, tint_)
                if d < best[0]:
                    best = (d, temp, tint_)
        # continuous refinement around the grid best (grid step is 20/15)
        t_lo = cal["temperature"]["values"][0]
        t_hi = cal["temperature"]["values"][-1]
        k_lo = cal["tint"]["values"][0]
        k_hi = cal["tint"]["values"][-1]
        t0, k0 = best[1], best[2]
        for _ in range(2):
            improved = False
            for dt in (-10, -5, 0, 5, 10):
                for dk in (-7.5, -3.75, 0, 3.75, 7.5):
                    t = _clamp(t0 + dt, t_lo, t_hi)
                    k_ = _clamp(k0 + dk, k_lo, k_hi)
                    d = dist_at(t, k_)
                    if d < best[0] - 1e-12:
                        best = (d, t, k_)
                        improved = True
            t0, k0 = best[1], best[2]
            if not improved:
                break
        return best[1], best[2]

    sat_amount, sat_factor = sat_estimate(0, 0)
    temperature, tint = wb_match(sat_factor)
    sat_amount, sat_factor = sat_estimate(temperature, tint)

    # ---------------- joint fit: exposure + levels + vignette + glow (pass A)
    def build_C(temp, tint_, sat):
        gains = [1.0] * len(quantiles)
        for sweep, val in (("temperature", temp), ("tint", tint_),
                           ("saturation", sat)):
            if val:
                g = _quantile_gains(cal, sweep, val, quantiles)
                gains = [gains[i] * g[i] for i in range(len(quantiles))]
        return gains

    grain_tail = 1.0
    if grain_section is not None:
        grain_tail = max(0.3, math.exp(-sigma / 0.08))
    tail_weight = [grain_tail if t <= 0.03 or t >= 0.97 else 1.0
                   for t in quantiles]

    def vig_gains_fn(amount):
        return _quantile_gains(cal, "vignette", amount, quantiles)

    def glo_gains_fn(amount):
        return _quantile_gains(cal, "glow", amount, quantiles)

    def run_fit(vig_center, glo_center, temp, tint_, sat, wide, split_map=None):
        C = build_C(temp, tint_, sat)
        if wide:
            vigs = {0.0, _clamp(vig_center, -3.0, 3.0)}
            for d in (-1.5, -1.0, -0.5, 0.5, 1.0, 1.5):
                vigs.add(_clamp(vig_center + d, -3.0, 3.0))
            glos = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25]
        else:
            vigs = {_clamp(vig_center + d, -3.0, 3.0)
                    for d in (-0.5, -0.25, 0.0, 0.25, 0.5)}
            glos = {_clamp(glo_center + d, 0.0, 1.5)
                    for d in (-0.3, -0.15, 0.0, 0.15, 0.3)}
        fit = ToneFit(q_ref, q_out, C, ref,
                      (frame.band_mass(0.90, 1.01), frame.band_mass(0.98, 1.01),
                       frame.band_mass(0.0, 0.02)), tail_weight,
                      radial_response, vig_gains_fn, glo_gains_fn,
                      vig_radial_fn, glo_radial_fn,
                      radial_pair=ref.radial_pair(), split_map=split_map,
                      q_t=quantiles)
        return fit.search(cal["exposure"], sorted(vigs), sorted(glos))

    fit = run_fit(vignette_prior, 0.0, temperature, tint,
                  sat_amount if abs(sat_amount) >= 5 else 0, wide=True)
    stops, gamma, ib, iw, ob, ow, vignette_amount, glow_intensity = fit[0:8]
    g_stops = _interp(cal["exposure"], stops, "mean_ratio")

    if abs(vignette_amount) >= EMIT["vignette"]:
        look["vignette"] = {"amount": round(vignette_amount, 2)}
        note("vignette", lambda:
              "The joint tone fit places the vignette at %.2f. The raw "
             "corner/center ratio alone suggested %.2f, but grain "
             "clipping, levels crush and glow bloom bias that reading; "
             "the fit reconciles it with the histogram. Negative darkens "
             "the edges."
             % (vignette_amount, vignette_prior),
             0.65 * base_conf)
    if glow_intensity >= EMIT["glow"]:
        look["glow"] = {"threshold": 180, "radius_px": 15,
                        "intensity": round(glow_intensity, 2)}
        note("glow", lambda:
             "Top-band bloom beyond what exposure and levels can explain "
             "fits Glow intensity %.2f (calibrated at threshold 180, "
             "radius 15; those two are defaults, tune by eye)."
             % glow_intensity,
             0.5 * base_conf)

    # ------------------------------------------- exposure / levels emission
    def emit_tone():
        if abs(stops) >= EMIT["exposure_stops"]:
            section = {"stops": round(stops, 2)}
            if abs(gamma - 1.0) >= EMIT["gamma"]:
                section["gamma"] = round(gamma, 2)
            look["exposure"] = section
        elif "exposure" in look:
            del look["exposure"]
        if (ib >= EMIT["in_black"] or iw <= EMIT["in_white"]
                or ob >= EMIT["out_black"] or ow <= EMIT["out_white"]):
            look["levels"] = {
                "input_black": round(ib, 3),
                "input_white": round(iw, 3),
                "output_black": round(ob, 3),
                "output_white": round(ow, 3),
            }
        elif "levels" in look:
            del look["levels"]
        if abs(vignette_amount) >= EMIT["vignette"]:
            look["vignette"] = {"amount": round(vignette_amount, 2)}
        elif "vignette" in look:
            del look["vignette"]
        if glow_intensity >= EMIT["glow"]:
            look["glow"] = {"threshold": 180, "radius_px": 15,
                            "intensity": round(glow_intensity, 2)}
        elif "glow" in look:
            del look["glow"]

    def emit_sat():
        if abs(sat_amount) >= EMIT["saturation"]:
            look["saturation"] = {"amount": round(sat_amount)}
        elif "saturation" in look:
            del look["saturation"]

    def compute_midslope():
        if ib + (1.0 - iw) + ob + (1.0 - ow) > 1e-6 or abs(stops) > 1e-6:
            m = (ow - ob) / max(1e-6, iw - ib) * g_stops
            if abs(gamma - 1.0) > 1e-6:
                m *= gamma * (0.5 ** (gamma - 1.0))
            return m
        return 1.0

    stops = round(stops, 2)
    emit_tone()
    if "exposure" in look:
        note("exposure", lambda:
             "A joint fit of the luminance quantile curve (searching "
             "vignette and glow alongside exposure/levels so bloom and "
             "corner falloff are not absorbed here) puts exposure at "
             "%.2f stops%s. The AE Exposure response is calibrated, not "
             "2^stops, so trust this number."
             % (stops, ", gamma %.2f" % gamma if abs(gamma - 1.0) >= 0.08
                else ""),
             0.6 * base_conf)
    if "levels" in look:
        note("levels", lambda:
             "The quantile curve also fits a Levels remap of input "
             "[%.3f, %.3f] to output [%.3f, %.3f]. Output fades (black lift "
             "/ white ceiling) and input contrast show up here; grain "
             "smears the extremes, so check the Levels histogram in AE."
             % (ib, iw, ob, ow),
             0.6 * base_conf)

    # --------------------------- white balance + saturation refinement (pass 2)
    temperature2, tint2 = wb_match(sat_factor)
    sat_amount2, sat_factor2 = sat_estimate(temperature2, tint2,
                                            compute_midslope())
    if (abs(temperature2 - temperature) >= 10 or abs(tint2 - tint) >= 8
            or abs(sat_amount2 - sat_amount) >= 5):
        temperature, tint = temperature2, tint2
        sat_amount, sat_factor = sat_amount2, sat_factor2
        fit = run_fit(vignette_amount, glow_intensity, temperature, tint,
                      sat_amount, wide=False)
        stops, gamma, ib, iw, ob, ow, vignette_amount, glow_intensity = fit[0:8]
        g_stops = _interp(cal["exposure"], stops, "mean_ratio")
        emit_tone()

    if abs(temperature) >= EMIT["temperature"] or abs(tint) >= EMIT["tint"]:
        look["white_balance"] = {"temperature": round(temperature),
                                 "tint": round(tint)}
        note("white_balance",
             "Mid-tone channel balance (region fixed by the reference, so "
             "split toning does not leak in) places temperature at %d and "
             "tint at %d (grid refined continuously, expect +-5). "
             "Saturation is divided out first."
             % (round(temperature), round(tint)),
             0.6 * base_conf)

    emit_sat()
    if "saturation" in look:
        note("saturation", lambda:
             "Mid-tone chroma is corrected for white-balance chroma gain "
             "and the levels/exposure slope, then inverted through the "
             "saturation calibration curve: amount %d."
             % round(sat_amount),
             0.6 * base_conf)

    # -------------------------------------------------------------- split tone
    def build_regions():
        regions = {}
        for label in ("dark", "mid", "bright"):
            base = ref.region_color(*REGION_BANDS[label])
            if base is None:
                continue
            x = [v / 255.0 for v in base]
            x = [(g_stops * v) ** gamma for v in x]
            x = [_levels_map(v, ib, iw, ob, ow) for v in x]
            for sweep, val in (("temperature", temperature), ("tint", tint)):
                if abs(val) >= 5:
                    x = [a * b for a, b in zip(x, _region_response(cal, sweep, val, label))]
            lum = _luma01(x)
            x = [lum + (c - lum) * sat_factor for c in x]
            for sweep, val in (("vignette", vignette_amount),
                               ("glow", glow_intensity),
                               ("blur", blur_radius if "blur" in look else 0.0),
                               (grain_key, grain_amount)):
                if abs(val) >= 0.01:
                    x = [a * b for a, b in zip(x, _region_response(cal, sweep, val, label))]
            y = frame.masked_region_color(ref, *REGION_BANDS[label])
            if y is None:
                continue
            regions[label] = (x, [v / 255.0 for v in y])
        return regions

    def solve_split(regions):
        if not regions:
            return None
        drifts = {label: math.sqrt(sum((y[c] - x[c]) ** 2 for c in range(3)))
                  for label, (x, y) in regions.items()}
        if max(drifts.values()) < EMIT["split_drift"]:
            return None
        resid, k, sol = _solve_split(regions)
        if k * 100.0 < EMIT["split_strength"]:
            return None
        cb = [_clamp(v, 0.0, 1.0) for v in sol[0:3]]
        cw = [_clamp(v, 0.0, 1.0) for v in sol[3:6]]

        def tone_chroma(c):
            lum = _luma01(c)
            return max(abs(c[i] - lum) for i in range(3))

        # a "tone" that is essentially gray is modeling a global shift
        # (exposure/white-balance slop), not split toning
        if max(tone_chroma(cb), tone_chroma(cw)) < EMIT["split_chroma"]:
            return None
        return k, cb, cw, drifts

    regions = build_regions()
    split = solve_split(regions)
    if split:
        k, cb, cw, drifts = split
        # Feedback: split toning acts on luma like an extra linear remap
        # (S-compression toward the tone-color luminances), which the fit
        # otherwise misreads as a levels output fade. Feed the solved map
        # back into the joint fit and re-solve until stable.
        for _ in range(2):
            a, b = _luma01(cb), _luma01(cw)
            sa = k * a
            sb = 1.0 - k + k * (b - a)
            fit = run_fit(vignette_amount, glow_intensity, temperature, tint,
                          sat_amount, wide=False, split_map=(sa, sb))
            stops, gamma, ib, iw, ob, ow, vignette_amount, glow_intensity = fit[0:8]
            g_stops = _interp(cal["exposure"], stops, "mean_ratio")
            # saturation re-estimate with the split's chroma effect at the
            # mid region divided out (toning shifts region chroma too)
            if "mid" in regions:
                x_mid = regions["mid"][0]
                lm = _luma01(x_mid)
                m_mid = [cb[i] + (cw[i] - cb[i]) * lm for i in range(3)]
                y_model = [x_mid[i] + k * (m_mid[i] - x_mid[i])
                           for i in range(3)]
                span_x = max(max(x_mid) - min(x_mid), 1e-6)
                scale = max(0.15, (max(y_model) - min(y_model)) / span_x)
                sat_amount2, sat_factor2 = sat_estimate(
                    temperature, tint, compute_midslope(),
                    measured=mid_chroma_img / scale)
                if abs(sat_amount2 - sat_amount) >= 5:
                    sat_amount, sat_factor = sat_amount2, sat_factor2
            regions = build_regions()
            nxt = solve_split(regions)
            if not nxt:
                split = None
                break
            k2, cb2, cw2, drifts2 = nxt
            stable = (abs(k2 - k) < 0.02
                      and max(abs(cb2[i] - cb[i]) for i in range(3)) < 0.02
                      and max(abs(cw2[i] - cw[i]) for i in range(3)) < 0.02)
            k, cb, cw, drifts = k2, cb2, cw2, drifts2
            if stable:
                break
        emit_tone()
        emit_sat()
        if split:
            strength = k * 100.0
            look["split_tone"] = {
                "shadows_hex": "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in cb),
                "highlights_hex": "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in cw),
                "strength": round(strength),
            }
            note("split_tone",
                 "Region-color drift (dark %.3f, mid %.3f, bright %.3f, "
                 "after correcting for every other estimated effect) solves "
                 "jointly for Tint strength %.0f with tone colors %s -> %s; "
                 "the tone curve is then fed back into the tone fit so it "
                 "does not masquerade as a Levels fade. Strength and tone "
                 "saturation trade off (drift = strength x tone distance), "
                 "so this is the least determined aspect — treat the colors "
                 "as starting points."
                 % (drifts.get("dark", 0), drifts.get("mid", 0),
                    drifts.get("bright", 0), strength,
                    look["split_tone"]["shadows_hex"],
                    look["split_tone"]["highlights_hex"]),
                 0.35 * base_conf)

    # Flush deferred notes now that every pass has finished, so quoted values
    # match the emitted look; drop notes whose section a later pass removed.
    for topic, message, confidence in pending_notes:
        if topic not in look:
            continue
        text = message() if callable(message) else message
        notes.append({"topic": topic, "message": text,
                      "confidence": round(confidence, 2)})
    confidences = [n["confidence"] for n in notes] or [0.5]
    analysis = {
        "schema_version": "1.0",
        "name": slug,
        "source": {
            "path": str(Path(image_path)),
            "type": "image",
            "width": frame.img.size[0],
            "height": frame.img.size[1],
            "frames": None,
        },
        "look": look,
        "notes": notes,
        "overall_confidence": round(sum(confidences) / len(confidences), 2),
    }
    if not has_ref:
        notes.append({"topic": "general", "confidence": 0.4,
                      "message": "No clean reference was given, so the calibration plate stood "
                      "in as the scene prior. Absolute values (exposure, levels, "
                      "white balance) are much less certain than relative ones "
                      "(grain, blur, vignette)."})
        analysis["overall_confidence"] = round(
            analysis["overall_confidence"] * CONFIDENCE_SCALE_STANDALONE, 2)
    return analysis


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", help="Image to analyze")
    parser.add_argument("--reference", help="Clean/ungraded plate of the same scene")
    parser.add_argument("--name", help="Slug for the look (default: image stem)")
    parser.add_argument("-o", "--output", help="Write analysis JSON here "
                        "(default: <image>.analysis.json)")
    args = parser.parse_args(argv)

    image = Path(args.image).expanduser().resolve()
    if not image.exists():
        parser.error("Image not found: %s" % image)
    reference = Path(args.reference).expanduser().resolve() if args.reference else None
    if reference is not None and not reference.exists():
        parser.error("Reference not found: %s" % reference)

    analysis = analyze(image, reference, name=args.name)
    errors = validate.validate(analysis)
    if errors:
        print("Generated analysis failed validation:", file=sys.stderr)
        for error in errors:
            print("  - %s" % error, file=sys.stderr)
        return 2

    out = (Path(args.output).expanduser() if args.output
           else image.parent / (image.stem + ".analysis.json"))
    if not str(out).endswith(".json"):
        out = out.with_suffix(".json")
    out.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(analysis, indent=2))
    print("\nWrote %s" % out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
