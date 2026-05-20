"""Stage 3 — per-well fluorescence readout.

WHAT THIS MODULE DOES, IN ONE PARAGRAPH:
    For each well (with center (x, y) and detected radius r), sample a small
    inner disk for "signal" and a thin outer ring for "local background".
    Report mean / median / std of the signal disk, the median of the background
    annulus, and the background-subtracted signal = (mean_signal - median_bg).
    Per-well intensity columns are appended to the wells dataframe by the
    caller and ultimately written to wells.csv.

SAMPLING GEOMETRY (all in pixels, with `r_well` = the median detected radius):

       ___________
      /           \\         ann_outer  ──┐  annulus (local bg)
     /   _______   \\        ann_inner  ──┘
    /   /       \\   \\        r_well      = trap-chamber rim region
    |   | SIGNAL |   |       margin    ──┐  excluded ring (avoids edge)
    |   |   .    |   |       r_signal  ──┘  inner disk used for signal
    \\   \\_______/   /
     \\             /
      \\___________/

  signal disk:  radius r_signal = r_well - margin
  excluded:     ring [r_signal .. r_well + ann_inner] (well rim + gap)
  bg annulus:   ring [r_well + ann_inner .. r_well + ann_outer]

WHY A SINGLE r_well (not per-well r):
    Hough returns a discretely-stepped radius per well, mostly 42 with some 38-46
    on our test image. Using the median for *every* well makes per-well means
    directly comparable — each is "mean intensity over an X-pixel disk",
    regardless of which integer radius Hough picked. The per-well r from
    detection is still saved as a column for traceability.

WHY ASYMMETRIC STATISTIC (mean signal − median bg):
    - SIGNAL = mean: standard fluorescence convention. The biological quantity
      of interest is "total photon counts over the cell area, divided by area",
      which is exactly the arithmetic mean.
    - BG = median: robust to a few outlier pixels in the annulus (e.g. dim halo
      from a neighboring well, dust speck, hot pixel). With ~3000-4000 px in
      the annulus, the median is a stable estimate of the local baseline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from skimage.draw import disk


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
# Coordinate convention used throughout this file:
#   x = column index (image-width direction)
#   y = row    index (image-height direction)
# `skimage.draw.disk` takes its center as (row, col) — i.e., (y, x) in image-coord
# language. Indexing `img[rr, cc]` follows the same row-then-column order.

def disk_indices(cy: float, cx: float, r: float, shape: tuple[int, int]):
    """Pixel indices for a filled disk of radius `r` centered at (cy, cx).

    Returns two 1-D arrays (rr, cc) suitable for fancy-indexing: `img[rr, cc]`.
    `shape=(H, W)` auto-clips indices to image bounds, so if a well sits near
    the edge we transparently get a partial disk (and the caller can detect
    that via `n_signal_px < expected`).
    """
    rr, cc = disk((cy, cx), r, shape=shape)
    return rr, cc


def annulus_indices(cy: float, cx: float, r_in: float, r_out: float,
                    shape: tuple[int, int]):
    """Pixel indices for the annular ring [r_in, r_out) around (cy, cx).

    Implementation: outer disk MINUS inner disk. Same clipping semantics as
    `disk_indices` — if the annulus is partly off-image, we just get whatever
    fits.
    """
    rr, cc = disk((cy, cx), r_out, shape=shape)
    # Squared distance keeps things fast and avoids a sqrt. We use strict `<`
    # so the boundary pixel itself is part of the annulus (consistent with
    # skimage's disk, which includes pixels whose center lies inside the radius).
    inner = (rr - cy) ** 2 + (cc - cx) ** 2 < r_in ** 2
    return rr[~inner], cc[~inner]


# --------------------------------------------------------------------------- #
# Pre-flight sanity check (warnings only; never throws)
# --------------------------------------------------------------------------- #
def preflight(wells: pd.DataFrame, r_well: float, margin: float,
              ann_inner: float, ann_outer: float, shape: tuple[int, int]):
    """Warn about geometry issues that could silently bias readouts.

    Checks performed:
      1. Could any well's bg-annulus reach into a neighbor's signal disk?
         (would contaminate the background estimate with the neighbor's cells)
      2. Does any well's signal disk extend beyond the image border?
         (mean is then computed over a smaller, incomplete disk)

    Returns a dict of diagnostic numbers (also useful for logging).
    NOTE: this function only emits warnings; it never raises and never modifies
    the wells DataFrame. The caller decides what to do with the warnings.
    """
    H, W = shape
    r_signal = max(1.0, r_well - margin)
    r_out = r_well + ann_outer

    info = {
        "r_signal": r_signal,
        "r_in": r_well + ann_inner,
        "r_out": r_out,
        # Expected pixel counts (continuous-area approximation; rasterized
        # counts may differ by ~r pixels due to the boundary).
        "expected_signal_px": float(np.pi * r_signal ** 2),
        "expected_bg_px": float(np.pi * (r_out ** 2 - (r_well + ann_inner) ** 2)),
        "warnings": [],
    }

    # --- (1) neighbor-contamination check ---
    # For each well, find its nearest neighbor. The annulus extends to r_out
    # from THIS well's center; the neighbor's signal disk starts at
    # (nn_dist - r_signal) from this well's center. If r_out exceeds that, our
    # bg ring reaches into the neighbor's cells and the bg estimate is corrupt.
    pts = wells[["x", "y"]].to_numpy(dtype=float)
    if len(pts) >= 2:
        tree = cKDTree(pts)
        # k=2 because the nearest neighbor at k=1 is the point itself
        d, _ = tree.query(pts, k=2)
        nn_dist = d[:, 1]
        clearance = nn_dist - r_signal
        info["min_neighbor_clearance"] = float(clearance.min())
        if r_out > clearance.min():
            n_bad = int(np.sum(r_out > clearance))
            info["warnings"].append(
                f"{n_bad}/{len(pts)} wells: bg annulus may reach into nearest "
                f"neighbor's signal disk (clearance min={clearance.min():.0f}, "
                f"r_out={r_out:.0f}). Consider lowering annulus_outer."
            )

    # --- (2) image-edge clipping check ---
    # `edge_clearance` per well = distance from center to the nearest image edge.
    # If that's smaller than r_signal, the signal disk gets clipped.
    xs = wells["x"].to_numpy(); ys = wells["y"].to_numpy()
    edge_clearance = np.minimum.reduce([xs, W - 1 - xs, ys, H - 1 - ys])
    n_partial_signal = int(np.sum(edge_clearance < r_signal))
    n_partial_bg = int(np.sum(edge_clearance < r_out))
    info["n_partial_signal"] = n_partial_signal
    info["n_partial_bg_only"] = max(0, n_partial_bg - n_partial_signal)
    if n_partial_signal:
        info["warnings"].append(
            f"{n_partial_signal} wells have signal disk clipped by image edge."
        )

    return info


# --------------------------------------------------------------------------- #
# Per-well measurement (one marker image)
# --------------------------------------------------------------------------- #
SUPPORTED_METRICS = {
    "mean", "median", "std", "bg_median", "signal", "signal_median",
    "n_signal_px", "n_bg_px", "partial_disk",
}


def measure_marker(img: np.ndarray, wells: pd.DataFrame, r_well: float,
                   margin: float, ann_inner: float, ann_outer: float
                   ) -> dict[str, np.ndarray]:
    """Per-well stats on a single marker image. See module docstring for geometry.

    Returns a dict of numpy arrays (one entry per well, in dataframe order):
      mean, median, std        : statistics over the signal disk
      bg_median                : median over the bg annulus
      signal                   : mean - bg_median        (primary readout)
      signal_median            : median - bg_median      (robust alt)
      n_signal_px, n_bg_px     : actual pixel counts (catches clipped/empty wells)
      partial_disk             : bool, True if signal disk was clipped at image edge
    """
    n = len(wells)
    out: dict[str, np.ndarray] = {
        "mean": np.full(n, np.nan),
        "median": np.full(n, np.nan),
        "std": np.full(n, np.nan),
        "bg_median": np.full(n, np.nan),
        "n_signal_px": np.zeros(n, dtype=int),
        "n_bg_px": np.zeros(n, dtype=int),
        "partial_disk": np.zeros(n, dtype=bool),
    }

    # Pre-compute radii for this run. The signal disk shrinks inward from r_well
    # by `margin`; the bg annulus expands outward by [ann_inner, ann_outer].
    # The gap between the two — `margin + ann_inner` pixels wide — is the
    # excluded "guard ring" that catches the trap-chamber rim + sub-pixel edge
    # artifacts and keeps them out of both signal and background.
    r_signal = max(1.0, r_well - margin)
    r_in = r_well + ann_inner
    r_out = r_well + ann_outer
    H, W = img.shape

    # Expected (unclipped) signal-disk pixel count. We build a reference disk
    # away from any image edge to get the exact rasterized count, then use it
    # below to flag wells whose disk got clipped.
    rr_ref, _ = disk((0.0, 0.0), r_signal)
    expected = len(rr_ref)

    # Iterate well-by-well. With ~100-150 wells per image this is plenty fast;
    # vectorizing across all wells would obscure the per-well clipping logic
    # without buying meaningful performance.
    for i, (_, w) in enumerate(wells.iterrows()):
        # --- signal disk ---
        rr, cc = disk_indices(w.y, w.x, r_signal, (H, W))
        if len(rr) == 0:
            # Center entirely outside the image; leave all stats as NaN.
            # In practice this never happens (wells come from a lattice fit
            # bounded by detections that ARE inside the image), but guarding
            # here is cheap and survives future changes.
            continue

        # Always upcast to float64 BEFORE reductions. The input is uint16 and
        # uint16.mean() happens to work, but uint16.sum() overflows above ~65k
        # pixels. Computing in float64 also keeps the per-well mean exact rather
        # than truncated.
        vals = img[rr, cc].astype(np.float64)
        out["mean"][i] = vals.mean()
        out["median"][i] = float(np.median(vals))
        out["std"][i] = vals.std()
        out["n_signal_px"][i] = len(rr)
        # If skimage's disk-clip kicked in (well near image edge), the actual
        # pixel count is less than the reference. Flag for downstream filtering.
        out["partial_disk"][i] = len(rr) < expected

        # --- bg annulus ---
        arr, acc = annulus_indices(w.y, w.x, r_in, r_out, (H, W))
        if len(arr) == 0:
            # Annulus fully outside the image; leave bg as NaN. The signal stats
            # above were still recorded — the signal disk had at least some
            # pixels even if the bg ring didn't.
            continue
        bvals = img[arr, acc].astype(np.float64)
        # Median (not mean) of the annulus. The annulus can pick up rare bright
        # outlier pixels — dim halos from neighbors, dust, hot pixels — and
        # median absorbs those without distortion. The mean would be biased high
        # whenever a single bright outlier appears.
        out["bg_median"][i] = float(np.median(bvals))
        out["n_bg_px"][i] = len(arr)

    # Derived metrics. Both are background-subtracted variants:
    #   signal        = mean - bg_median   (primary; standard fluorescence quant)
    #   signal_median = median - bg_median (robust alt; use when bright outliers
    #                                       inside the well inflate the mean)
    out["signal"] = out["mean"] - out["bg_median"]
    out["signal_median"] = out["median"] - out["bg_median"]
    return out


def attach_metrics(wells: pd.DataFrame, marker: str,
                   metrics_dict: dict[str, np.ndarray],
                   requested: list[str]) -> None:
    """Write the requested per-marker columns into `wells` in place.

    Only metrics listed in `requested` get attached, so the user can keep the
    output CSV narrow by selecting just what they need in config.readout.metrics.
    """
    unknown = set(requested) - SUPPORTED_METRICS
    if unknown:
        raise ValueError(f"unknown metric(s) requested for {marker}: {sorted(unknown)}")
    for m in requested:
        # Column naming: `<metric>_<marker>` (e.g. `mean_green`, `signal_red`).
        wells[f"{m}_{marker}"] = metrics_dict[m]
