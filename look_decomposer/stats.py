"""Pixel statistics for the Look Decomposer analyzer.

PIL-only (no numpy in this environment). Global statistics run on a
downscaled copy; grain/blur statistics sample fixed windows at full
resolution so high-frequency detail survives the downscale.
"""

from PIL import Image

SMALL_W = 320
SMALL_H = 180


def luma(r, g, b):
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def chroma(r, g, b):
    return (max(r, g, b) - min(r, g, b)) / 255.0


def _median(values):
    values = sorted(values)
    n = len(values)
    if n == 0:
        return 0.0
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2.0


class Frame:
    """Cached measurements for one image."""

    def __init__(self, source):
        if isinstance(source, Image.Image):
            self.img = source.convert("RGB")
        else:
            self.img = Image.open(source).convert("RGB")
        self.small = self.img.resize((SMALL_W, SMALL_H), Image.BILINEAR)
        self._cache = {}

    def _compute(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def _small_luma(self):
        def fn():
            px = self.small.load()
            w, h = self.small.size
            out = []
            for y in range(h):
                for x in range(w):
                    r, g, b = px[x, y]
                    out.append(luma(r, g, b))
            return out
        return self._compute("small_luma", fn)

    def _small_rgb(self):
        def fn():
            px = self.small.load()
            w, h = self.small.size
            out = []
            for y in range(h):
                for x in range(w):
                    out.append(px[x, y])
            return out
        return self._compute("small_rgb", fn)

    def _radii(self):
        def fn():
            w, h = self.small.size
            cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
            out = []
            for y in range(h):
                dy = (y - cy) / (h / 2.0)
                for x in range(w):
                    dx = (x - cx) / (w / 2.0)
                    out.append((dx * dx + dy * dy) ** 0.5)
            return out
        return self._compute("radii", fn)

    def _center_indices(self):
        radii = self._radii()
        return [i for i, r in enumerate(radii) if r < 0.6]

    def mean_luma(self):
        def fn():
            lums = self._small_luma()
            idx = self._center_indices()
            return sum(lums[i] for i in idx) / max(1, len(idx))
        return self._compute("mean_luma", fn)

    def channel_means(self):
        def fn():
            rgbs = self._small_rgb()
            idx = self._center_indices()
            n = max(1, len(idx))
            return tuple(sum(rgbs[i][c] for i in idx) / n for c in range(3))
        return self._compute("channel_means", fn)

    def chroma_mean(self):
        def fn():
            rgbs = self._small_rgb()
            idx = self._center_indices()
            n = max(1, len(idx))
            return sum(chroma(*rgbs[i]) for i in idx) / n
        return self._compute("chroma_mean", fn)

    def _histogram(self):
        def fn():
            hist = [0] * 256
            for lum in self._small_luma():
                bin_index = int(lum * 255)
                if bin_index < 0:
                    bin_index = 0
                elif bin_index > 255:
                    bin_index = 255
                hist[bin_index] += 1
            return hist
        return self._compute("histogram", fn)

    def band_mass(self, lo, hi):
        hist = self._histogram()
        total = sum(hist)
        return sum(hist[i] for i in range(256)
                   if lo <= i / 255.0 < hi) / max(1, total)

    def quantile(self, q):
        """Luma value at cumulative fraction q (0..1) of the small image."""
        hist = self._histogram()
        total = sum(hist)
        target = q * total
        cum = 0
        for i in range(256):
            cum += hist[i]
            if cum >= target:
                return i / 255.0
        return 1.0

    def percentile_luma(self, p):
        return self.quantile(p / 100.0)

    def region_color(self, lo, hi):
        """Mean RGB of small pixels whose luma is in [lo, hi)."""
        rgbs = self._small_rgb()
        lums = self._small_luma()
        rs = gs = bs = n = 0
        for i, lum in enumerate(lums):
            if lo <= lum < hi:
                r, g, b = rgbs[i]
                rs += r
                gs += g
                bs += b
                n += 1
        if n == 0:
            return None
        return (rs / n, gs / n, bs / n)

    def radial_pair(self):
        """(outer median, center median) luma in 0-1, for radial models."""
        def fn():
            lums = self._small_luma()
            radii = self._radii()
            inner = [l for l, r in zip(lums, radii) if r < 0.5]
            outer = [l for l, r in zip(lums, radii) if r > 1.1]
            if not inner or not outer:
                return (0.5, 0.5)
            return (_median(outer), _median(inner))
        return self._compute("radial_pair", fn)

    def radial_ratio(self):
        """Median luma of outer region divided by median of center disc.

        Medians make the ratio robust to grain clipping in dark corners.
        """
        def fn():
            outer, inner = self.radial_pair()
            return outer / max(1e-6, inner)
        return self._compute("radial_ratio", fn)

    def region_chroma(self, lo, hi):
        """Mean chroma of small pixels whose luma is in [lo, hi)."""
        rgbs = self._small_rgb()
        lums = self._small_luma()
        vals = [chroma(*rgbs[i]) for i, lum in enumerate(lums) if lo <= lum < hi]
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    def masked_region_color(self, mask, lo, hi):
        """Mean RGB of pixels whose luma in the *mask* frame is in [lo, hi).

        Region membership defined by a clean reference keeps the same scene
        pixels selected across tone shifts (split toning moves pixels in and
        out of absolute luma bands).
        """
        if mask.small.size != self.small.size:
            raise ValueError("masked_region_color: frames differ in size")
        rgbs = self._small_rgb()
        mask_lums = mask._small_luma()
        rs = gs = bs = n = 0
        for i, lum in enumerate(mask_lums):
            if lo <= lum < hi:
                r, g, b = rgbs[i]
                rs += r
                gs += g
                bs += b
                n += 1
        if n == 0:
            return None
        return (rs / n, gs / n, bs / n)

    def masked_region_chroma(self, mask, lo, hi):
        """Mean chroma over pixels selected by the mask frame's luma band."""
        if mask.small.size != self.small.size:
            raise ValueError("masked_region_chroma: frames differ in size")
        rgbs = self._small_rgb()
        mask_lums = mask._small_luma()
        vals = [chroma(*rgbs[i]) for i, lum in enumerate(mask_lums)
                if lo <= lum < hi]
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    def _windows(self, win, step):
        px = self.img.load()
        w, h = self.img.size
        for y0 in range(step // 2, h - win - step // 2, step):
            for x0 in range(step // 2, w - win - step // 2, step):
                grid = []
                for y in range(y0, y0 + win):
                    row = []
                    for x in range(x0, x0 + win):
                        r, g, b = px[x, y]
                        row.append((r, g, b))
                    grid.append(row)
                yield grid

    def hf_window_values(self):
        """Brightness-normalized Laplacian energy per sample window.

        The window grid is deterministic, so index i always refers to the
        same image region — the analyzer can restrict measurements to
        windows that carry detail in a reference frame.
        """
        def fn():
            vals = []
            for grid in self._windows(32, 96):
                lum = [[luma(*p) for p in row] for row in grid]
                mean = sum(sum(r) for r in lum) / (len(lum) * len(lum[0]))
                res = n = 0
                for yy in range(1, len(lum) - 1):
                    for xx in range(1, len(lum[0]) - 1):
                        c = lum[yy][xx]
                        res += abs(4 * c - lum[yy - 1][xx] - lum[yy + 1][xx]
                                   - lum[yy][xx - 1] - lum[yy][xx + 1])
                        n += 1
                if n:
                    vals.append((res / n) / (mean + 0.02))
            return vals
        return self._compute("hf_window_values", fn)

    def hf_energy(self):
        """Median Laplacian energy at full resolution (all windows)."""
        def fn():
            return _median(self.hf_window_values())
        return self._compute("hf_energy", fn)

    def detail_hf(self, detail_values):
        """Mean HF over the windows marked as detail by a reference frame."""
        vals = self.hf_window_values()
        selected = [vals[i] for i in detail_values if i < len(vals)]
        if not selected:
            return _median(vals)
        return sum(selected) / len(selected)

    @staticmethod
    def detail_indices(window_values, factor=2.0):
        """Indices of windows carrying at least factor x the median energy."""
        med = _median(window_values)
        return [i for i, v in enumerate(window_values) if v >= factor * med and v > 0]

    def noise_std(self):
        """Median adjacent-pixel luma difference (grain-sensitive)."""
        def fn():
            vals = []
            for grid in self._windows(24, 128):
                lum = [[luma(*p) for p in row] for row in grid]
                diffs = []
                for yy in range(len(lum)):
                    for xx in range(len(lum[0]) - 1):
                        diffs.append(abs(lum[yy][xx] - lum[yy][xx + 1]))
                if diffs:
                    vals.append(_median(diffs) / (2 ** 0.5))
            return _median(vals)
        return self._compute("noise_std", fn)

    def chroma_noise_std(self):
        """Median adjacent-pixel chroma difference (color-noise sensitive)."""
        def fn():
            vals = []
            for grid in self._windows(24, 128):
                sat = [[chroma(*p) for p in row] for row in grid]
                diffs = []
                for yy in range(len(sat)):
                    for xx in range(len(sat[0]) - 1):
                        diffs.append(abs(sat[yy][xx] - sat[yy][xx + 1]))
                if diffs:
                    vals.append(_median(diffs) / (2 ** 0.5))
            return _median(vals)
        return self._compute("chroma_noise_std", fn)

    def summary(self):
        return {
            "mean_luma": round(self.mean_luma(), 4),
            "channels": [round(v / 255.0, 4) for v in self.channel_means()],
            "chroma": round(self.chroma_mean(), 4),
            "hf_energy": round(self.hf_energy(), 5),
            "noise_std": round(self.noise_std(), 5),
            "radial_ratio": round(self.radial_ratio(), 4),
        }


def invert_curve(xs, ys, y):
    """x such that the piecewise-linear curve through (xs, ys) hits y."""
    increasing = ys[-1] >= ys[0]
    if increasing and y <= ys[0]:
        return xs[0]
    if increasing and y >= ys[-1]:
        return xs[-1]
    if not increasing and y >= ys[0]:
        return xs[0]
    if not increasing and y <= ys[-1]:
        return xs[-1]
    for i in range(len(ys) - 1):
        y0, y1 = ys[i], ys[i + 1]
        if (y0 <= y <= y1) or (y1 <= y <= y0):
            if y1 == y0:
                return xs[i]
            t = (y - y0) / (y1 - y0)
            return xs[i] + t * (xs[i + 1] - xs[i])
    return xs[-1]
