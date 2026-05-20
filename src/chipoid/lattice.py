"""Stage 2 — axis-aligned lattice fit, snap, and fill.

Assumes detections come from a roughly regular grid that is approximately
axis-aligned with the image axes (no rotation). Multi-chip clustering is NOT
attempted here; if a single image contains multiple physically separate chips
they must be split upstream.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


def estimate_pitches(centers: pd.DataFrame, k_nn: int = 4,
                     axis_band: float = 50.0) -> tuple[float, float]:
    """From detected centers, estimate (col_pitch_x, row_pitch_y).

    Approach: for each center, collect vectors to its k nearest neighbors. Keep
    only the half-plane vectors (x > 0, or x == 0 with y > 0) so each edge is
    counted once. Then:
      - horizontal-ish vectors (|dy| < axis_band) -> median dx = col pitch
      - vertical-ish   vectors (|dx| < axis_band) -> median |dy| = row pitch
    """
    pts = centers[["x", "y"]].to_numpy(dtype=float)
    tree = cKDTree(pts)
    # +1 because k=1 returns the point itself
    _, idxs = tree.query(pts, k=k_nn + 1)
    dx_all, dy_all = [], []
    for i in range(len(pts)):
        for j in idxs[i, 1:]:
            v = pts[j] - pts[i]
            if v[0] > 0 or (abs(v[0]) < 1e-6 and v[1] > 0):
                dx_all.append(v[0]); dy_all.append(v[1])
    dx_all = np.asarray(dx_all); dy_all = np.asarray(dy_all)

    horiz = np.abs(dy_all) < axis_band
    col_pitch = float(np.median(dx_all[horiz])) if horiz.any() else float("nan")

    vert = np.abs(dx_all) < axis_band
    row_pitch = float(np.median(np.abs(dy_all[vert]))) if vert.any() else float("nan")
    return col_pitch, row_pitch


def estimate_origin(centers: pd.DataFrame, col_pitch: float, row_pitch: float
                    ) -> tuple[float, float]:
    """Lattice origin = circular mean of (x mod col_pitch, y mod row_pitch).

    Using a circular mean instead of a plain modulo-then-mean handles the
    wrap-around correctly when detections straddle a pitch boundary.
    """
    xs = centers["x"].to_numpy(dtype=float)
    ys = centers["y"].to_numpy(dtype=float)
    theta_x = (xs / col_pitch) * 2 * np.pi
    theta_y = (ys / row_pitch) * 2 * np.pi
    cx = float(np.angle(np.exp(1j * theta_x).mean()) / (2 * np.pi)) * col_pitch
    cy = float(np.angle(np.exp(1j * theta_y).mean()) / (2 * np.pi)) * row_pitch
    if cx < 0: cx += col_pitch
    if cy < 0: cy += row_pitch
    return cx, cy


def generate_grid(centers: pd.DataFrame, col_pitch: float, row_pitch: float,
                  x0: float, y0: float, image_shape: tuple[int, int]
                  ) -> list[tuple[int, int, float, float]]:
    """Predict all grid points inside the bbox of detections (+/- 0.5 pitch)."""
    H, W = image_shape
    xs = centers["x"].to_numpy(); ys = centers["y"].to_numpy()
    xmin = max(0.0, xs.min() - 0.5 * col_pitch)
    xmax = min(W - 1.0, xs.max() + 0.5 * col_pitch)
    ymin = max(0.0, ys.min() - 0.5 * row_pitch)
    ymax = min(H - 1.0, ys.max() + 0.5 * row_pitch)

    j_min = int(np.ceil((xmin - x0) / col_pitch))
    j_max = int(np.floor((xmax - x0) / col_pitch))
    i_min = int(np.ceil((ymin - y0) / row_pitch))
    i_max = int(np.floor((ymax - y0) / row_pitch))

    pts = []
    for i in range(i_min, i_max + 1):
        for j in range(j_min, j_max + 1):
            x = x0 + j * col_pitch
            y = y0 + i * row_pitch
            if 0 <= x < W and 0 <= y < H:
                pts.append((i, j, x, y))
    return pts


def snap_to_lattice(grid_pts, centers: pd.DataFrame,
                    snap_tol: float, default_r: float) -> pd.DataFrame:
    """For each grid point, attach the nearest detection if within snap_tol.

    Wells where no detection is within tolerance fall back to the grid-predicted
    position and a default radius; their `source` column is "filled".
    """
    pts = centers[["x", "y"]].to_numpy(dtype=float)
    tree = cKDTree(pts)
    rows = []
    for (i, j, gx, gy) in grid_pts:
        d, k = tree.query([gx, gy], k=1)
        if d <= snap_tol:
            r = float(centers.iloc[k]["r"])
            x = float(centers.iloc[k]["x"])
            y = float(centers.iloc[k]["y"])
            src = "detected"
        else:
            r = default_r; x = float(gx); y = float(gy); src = "filled"
        rows.append((i, j, x, y, r, src, float(d)))
    df = pd.DataFrame(rows, columns=["row", "col", "x", "y", "r", "source", "dist_to_det"])
    # Normalize row/col so the smallest is 0 (consistent across images).
    df["row"] -= df["row"].min(); df["col"] -= df["col"].min()
    df.insert(0, "well_id", [f"r{int(r):02d}c{int(c):02d}" for r, c in zip(df.row, df.col)])
    return df


def fit_lattice(centers: pd.DataFrame, image_shape: tuple[int, int], *,
                k_nn: int = 4, axis_band: float = 50.0,
                snap_tolerance: float = 30.0
                ) -> tuple[pd.DataFrame, dict]:
    """Run the full lattice stage and return (wells_df, info_dict)."""
    col_pitch, row_pitch = estimate_pitches(centers, k_nn=k_nn, axis_band=axis_band)
    x0, y0 = estimate_origin(centers, col_pitch, row_pitch)
    grid_pts = generate_grid(centers, col_pitch, row_pitch, x0, y0, image_shape)
    default_r = float(np.median(centers["r"]))
    wells = snap_to_lattice(grid_pts, centers, snap_tolerance, default_r)
    info = {
        "col_pitch": col_pitch, "row_pitch": row_pitch,
        "x0": x0, "y0": y0, "default_r": default_r,
        "n_grid": len(grid_pts),
        "n_detected": int((wells.source == "detected").sum()),
        "n_filled": int((wells.source == "filled").sum()),
    }
    return wells, info
