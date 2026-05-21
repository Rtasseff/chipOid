"""Stage 2 — lattice fit, snap, fill, and trim.

Detections come from a roughly regular grid that may be slightly rotated
relative to the image axes. The lattice fit:
  1. Estimates the rotation angle θ from nearest-neighbor vectors (robust to
     outliers via circular-statistics median).
  2. De-rotates the detections to an axis-aligned frame.
  3. Fits an axis-aligned lattice (row pitch, col pitch, origin) in that frame.
  4. Generates the predicted grid in the de-rotated frame.
  5. Snaps detections to the grid (or marks "filled" if Hough missed a well).
  6. Rotates well positions back to the original image frame.
  7. Trims spurious rows/cols where the detector saw no real wells, and
     optionally hard-caps the lattice dimensions.

Multi-chip clustering is NOT attempted; one lattice per image.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


# --------------------------------------------------------------------------- #
# Rotation
# --------------------------------------------------------------------------- #
def estimate_rotation(centers: pd.DataFrame, k_nn: int = 4,
                      dist_tol: float = 1.4) -> float:
    """Estimate lattice rotation in radians, in (-π/4, π/4].

    For a rectangular grid rotated by θ, NN vectors point near θ, θ+π/2, θ+π,
    θ+3π/2. We fold all angles into [0, π/2) (because of the 4-fold symmetry
    of a rectangular grid) and take a circular mean.

    Outlier rejection:
      Edge/corner wells lose some of their lattice neighbors, so their k-th
      NN may be a DIAGONAL well rather than a row/col neighbor. Diagonal NN
      vectors carry the wrong angle (~atan2(row_pitch, col_pitch) instead of
      0/π/2) and bias the mean.

      Fix: filter per-point. For each well, find its single closest neighbor
      (distance d_min). Keep only NN vectors of length <= dist_tol * d_min.
      With dist_tol = 1.4 (default), a grid where col_pitch/row_pitch <= 1.4
      keeps both row and col neighbors (whose distance ratio is ~1.0 to 1.4)
      and excludes diagonals (distance ~sqrt(2) * row_pitch ≈ 1.41 * row_pitch
      in a square lattice, larger for elongated). Even for very elongated
      lattices the filter still keeps the short-pitch neighbors, which is
      enough for the rotation estimate.
    """
    pts = centers[["x", "y"]].to_numpy(dtype=float)
    if len(pts) < 2:
        return 0.0
    tree = cKDTree(pts)
    k = min(k_nn + 1, len(pts))
    dists, idxs = tree.query(pts, k=k)
    angles: list[float] = []
    for i in range(len(pts)):
        d_min = dists[i, 1]  # closest non-self neighbor distance
        cutoff = dist_tol * d_min
        for n in range(1, k):
            if dists[i, n] > cutoff:
                continue
            j = idxs[i, n]
            v = pts[j] - pts[i]
            angles.append(np.arctan2(v[1], v[0]) % (np.pi / 2))
    if not angles:
        return 0.0
    angles = np.asarray(angles)
    # Map [0, π/2) onto the unit circle by multiplying angle by 4 (period π/2
    # becomes period 2π). Take the resultant vector's angle, then divide by 4
    # to recover the lattice-frame rotation. Standard circular-mean construction.
    z = np.exp(4j * angles)
    theta = np.angle(z.mean()) / 4.0
    # Center in (-π/4, π/4]
    if theta > np.pi / 4:
        theta -= np.pi / 2
    elif theta <= -np.pi / 4:
        theta += np.pi / 2
    return float(theta)


def _rotate_xy(xy: np.ndarray, angle: float, pivot: np.ndarray) -> np.ndarray:
    """Rotate Nx2 array of (x,y) points by `angle` rad around `pivot`."""
    c, s = np.cos(angle), np.sin(angle)
    R = np.array([[c, -s], [s, c]])
    return (xy - pivot) @ R.T + pivot


# --------------------------------------------------------------------------- #
# Pitch + origin + grid + snap (all done in an axis-aligned working frame)
# --------------------------------------------------------------------------- #
def estimate_pitches(centers: pd.DataFrame, k_nn: int = 4,
                     axis_band: float = 50.0) -> tuple[float, float]:
    """From axis-aligned detections, estimate (col_pitch_x, row_pitch_y)."""
    pts = centers[["x", "y"]].to_numpy(dtype=float)
    tree = cKDTree(pts)
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
    """Lattice origin = circular mean of (x mod col_pitch, y mod row_pitch)."""
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
                  x0: float, y0: float
                  ) -> list[tuple[int, int, float, float]]:
    """Predict all grid points inside the bbox of detections (+/- 0.5 pitch).

    Bounds use only the detection bbox (NOT the image bounds). After rotation
    back to the original frame, the image-bounds check happens in the snap
    step where it matters.
    """
    xs = centers["x"].to_numpy(); ys = centers["y"].to_numpy()
    xmin = xs.min() - 0.5 * col_pitch; xmax = xs.max() + 0.5 * col_pitch
    ymin = ys.min() - 0.5 * row_pitch; ymax = ys.max() + 0.5 * row_pitch
    j_min = int(np.ceil((xmin - x0) / col_pitch))
    j_max = int(np.floor((xmax - x0) / col_pitch))
    i_min = int(np.ceil((ymin - y0) / row_pitch))
    i_max = int(np.floor((ymax - y0) / row_pitch))
    pts = []
    for i in range(i_min, i_max + 1):
        for j in range(j_min, j_max + 1):
            pts.append((i, j, x0 + j * col_pitch, y0 + i * row_pitch))
    return pts


def snap_to_lattice(grid_pts, centers: pd.DataFrame,
                    snap_tol: float, default_r: float) -> pd.DataFrame:
    """For each grid point, attach the nearest detection if within snap_tol."""
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
    return pd.DataFrame(rows, columns=["row", "col", "x", "y", "r", "source", "dist_to_det"])


# --------------------------------------------------------------------------- #
# Trim + renumber
# --------------------------------------------------------------------------- #
def _renumber_and_label(wells: pd.DataFrame) -> pd.DataFrame:
    """Reset row/col to start at 0 and regenerate well_id labels."""
    if len(wells) == 0:
        return wells
    wells = wells.copy()
    wells["row"] -= wells["row"].min()
    wells["col"] -= wells["col"].min()
    wells.insert(0, "well_id", [f"r{int(r):02d}c{int(c):02d}"
                                for r, c in zip(wells.row, wells.col)])
    return wells


def trim_lattice(wells: pd.DataFrame,
                 min_detected_fraction: float = 0.25,
                 max_rows: int | None = None,
                 max_cols: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Drop rows/cols whose Hough-detection density falls below a threshold,
    and optionally hard-cap to a maximum number of rows/cols.

    Density filter: for each row, fraction = #detected / #total. Rows below
    `min_detected_fraction` are dropped. Same for cols. Set to 0 to disable.

    Hard caps: highest-index rows/cols trimmed first. None disables.
    """
    info: dict = {"trimmed_rows": [], "trimmed_cols": []}
    if len(wells) == 0:
        return wells, info

    if min_detected_fraction > 0:
        for axis in ("row", "col"):
            detected_per = wells[wells.source == "detected"].groupby(axis).size()
            total_per = wells.groupby(axis).size()
            frac = (detected_per.reindex(total_per.index, fill_value=0) / total_per)
            drop = frac[frac < min_detected_fraction].index.tolist()
            if drop:
                info[f"trimmed_{axis}s"] = drop
                wells = wells[~wells[axis].isin(drop)]

    if max_rows is not None and wells["row"].nunique() > max_rows:
        tmp = _renumber_and_label(wells)
        keep_rows = sorted(tmp["row"].unique())[:max_rows]
        info["capped_rows_kept"] = keep_rows
        wells = tmp[tmp["row"].isin(keep_rows)]
    if max_cols is not None and wells["col"].nunique() > max_cols:
        tmp = _renumber_and_label(wells)
        keep_cols = sorted(tmp["col"].unique())[:max_cols]
        info["capped_cols_kept"] = keep_cols
        wells = tmp[tmp["col"].isin(keep_cols)]

    wells = _renumber_and_label(wells)
    return wells, info


# --------------------------------------------------------------------------- #
# Top-level entry
# --------------------------------------------------------------------------- #
def fit_lattice(centers: pd.DataFrame, image_shape: tuple[int, int], *,
                k_nn: int = 4, axis_band: float = 50.0,
                snap_tolerance: float = 30.0,
                rotation_deg: str | float = "auto",
                min_detected_fraction: float = 0.25,
                max_rows: int | None = None,
                max_cols: int | None = None,
                ) -> tuple[pd.DataFrame, dict]:
    """Run the full lattice stage and return (wells_df, info_dict).

    `rotation_deg`:
      - "auto" (default): estimate rotation from data via circular-statistics
        median of NN-vector angles.
      - numeric: use the given rotation in DEGREES (positive = counter-clockwise
        in image coords). Use 0 to force pure axis-aligned behavior.
    """
    # --- determine rotation ---
    if isinstance(rotation_deg, str) and rotation_deg.lower() == "auto":
        theta = estimate_rotation(centers, k_nn=k_nn)
        rotation_source = "auto"
    else:
        theta = float(np.radians(float(rotation_deg)))
        rotation_source = "manual"

    # --- de-rotate detections to an axis-aligned working frame ---
    # Rotate around the centroid of detections so coordinates stay in roughly
    # the same range (avoids creating huge negative values).
    pivot = centers[["x", "y"]].to_numpy(dtype=float).mean(axis=0)
    pts_aa = _rotate_xy(centers[["x", "y"]].to_numpy(dtype=float), -theta, pivot)
    centers_aa = centers.copy()
    centers_aa["x"] = pts_aa[:, 0]
    centers_aa["y"] = pts_aa[:, 1]

    # --- fit axis-aligned lattice in the rotated frame ---
    col_pitch, row_pitch = estimate_pitches(centers_aa, k_nn=k_nn, axis_band=axis_band)
    x0, y0 = estimate_origin(centers_aa, col_pitch, row_pitch)
    grid_pts = generate_grid(centers_aa, col_pitch, row_pitch, x0, y0)
    default_r = float(np.median(centers["r"]))
    wells = snap_to_lattice(grid_pts, centers_aa, snap_tolerance, default_r)

    # --- rotate well positions back to the original image frame ---
    pts_back = _rotate_xy(wells[["x", "y"]].to_numpy(dtype=float), theta, pivot)
    wells["x"] = pts_back[:, 0]
    wells["y"] = pts_back[:, 1]

    n_before = len(wells)
    n_det_before = int((wells.source == "detected").sum())

    # --- trim ---
    wells, trim_info = trim_lattice(
        wells,
        min_detected_fraction=min_detected_fraction,
        max_rows=max_rows, max_cols=max_cols,
    )

    info = {
        "col_pitch": col_pitch, "row_pitch": row_pitch,
        "x0": x0, "y0": y0, "default_r": default_r,
        "rotation_deg": float(np.degrees(theta)),
        "rotation_source": rotation_source,
        "n_grid": len(grid_pts),
        "n_detected": int((wells.source == "detected").sum()),
        "n_filled": int((wells.source == "filled").sum()),
        "n_before_trim": n_before,
        "n_detected_before_trim": n_det_before,
        "n_trimmed": n_before - len(wells),
        **trim_info,
    }
    return wells, info
