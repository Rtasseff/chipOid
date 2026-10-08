"""Stage 2 — lattice fit, snap, fill, and trim.

Detections come from a roughly regular grid that may be slightly rotated
relative to the image axes. The lattice fit:
  1. Estimates the rotation angle θ from nearest-neighbor vectors (circular
     mean after a per-point distance filter).
  2. De-rotates the detections to an axis-aligned frame.
  3. Fits an axis-aligned lattice (row pitch, col pitch, origin) in that frame
     and generates the predicted grid; this seeds the grid indices (i, j).
  4. Snaps detections to the grid (unique, one detection per grid point).
  5. Refits an affine (i, j) -> (x, y) by least squares in the image frame and
     re-snaps, up to 3 times. The median pitch from step 3 drifts when row
     spacing alternates; the affine uses the mean period and absorbs shear.
  6. Rescues unassigned grid points with an unused detection within r; the
     rest are "filled" at the predicted position. Detected wells keep their
     exact Hough x, y, r.
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
    if len(pts) < 2:
        return float("nan"), float("nan")
    tree = cKDTree(pts)
    _, idxs = tree.query(pts, k=min(k_nn + 1, len(pts)))
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
    """For each grid point, attach the nearest detection if within snap_tol.

    Legacy, non-unique snap (one detection may serve two grid points). Kept
    for reference and ad-hoc use; `fit_lattice` uses `_assign_unique`.
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
    return pd.DataFrame(rows, columns=["row", "col", "x", "y", "r", "source", "dist_to_det"])


def _assign_unique(grid_xy: np.ndarray, det_xy: np.ndarray, tol: float,
                   grid_taken: np.ndarray | None = None,
                   det_taken: np.ndarray | None = None) -> np.ndarray:
    """Greedy unique assignment of detections to grid points.

    Takes every (grid point, detection) pair with distance <= tol, sorts by
    distance (ties broken by grid index, then detection index, so the result
    is deterministic) and accepts a pair only if neither side is taken yet.
    Returns `assign`: for each grid point, the detection index or -1.
    `grid_taken` / `det_taken` mark points already used by an earlier pass.
    """
    n_g = len(grid_xy)
    assign = np.full(n_g, -1, dtype=int)
    if n_g == 0 or len(det_xy) == 0:
        return assign
    g_used = np.zeros(n_g, bool) if grid_taken is None else grid_taken.copy()
    d_used = np.zeros(len(det_xy), bool) if det_taken is None else det_taken.copy()
    sdm = cKDTree(grid_xy).sparse_distance_matrix(
        cKDTree(det_xy), tol, output_type="ndarray")
    if len(sdm) == 0:
        return assign
    order = np.lexsort((sdm["j"], sdm["i"], sdm["v"]))
    for gi, dk in zip(sdm["i"][order], sdm["j"][order]):
        if g_used[gi] or d_used[dk]:
            continue
        assign[gi] = dk
        g_used[gi] = True
        d_used[dk] = True
    return assign


def _affine_predict(P: np.ndarray, ij: np.ndarray) -> np.ndarray:
    """Grid indices (N,2) of (i=row, j=col) -> image (x, y) via P (3x2)."""
    return np.column_stack([np.ones(len(ij)), ij]) @ P


def _affine_grid(P: np.ndarray, det_xy: np.ndarray) -> np.ndarray:
    """All integer (i, j) spanned by the detections under the affine P.

    Each detection is mapped back to lattice coordinates with the inverse
    affine and rounded; the grid is the full i_min..i_max x j_min..j_max box.
    """
    A = P[1:].T  # columns: a (row step), b (col step)
    ij = np.linalg.solve(A, (det_xy - P[0]).T).T
    ij = np.rint(ij).astype(int)
    i_min, j_min = ij.min(axis=0)
    i_max, j_max = ij.max(axis=0)
    ii, jj = np.meshgrid(np.arange(i_min, i_max + 1),
                         np.arange(j_min, j_max + 1), indexing="ij")
    return np.column_stack([ii.ravel(), jj.ravel()])


# --------------------------------------------------------------------------- #
# Trim + renumber
# --------------------------------------------------------------------------- #
def _renumber_and_label(wells: pd.DataFrame) -> pd.DataFrame:
    """Reset row/col to start at 0 and regenerate well_id labels."""
    if len(wells) == 0:
        return wells
    # Drop a stale label: when a max_rows cap has already renumbered, the
    # max_cols cap or the final renumber would otherwise fail on insert.
    wells = wells.drop(columns="well_id", errors="ignore")
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
        info["capped_rows_total"] = int(tmp["row"].nunique())
        wells = tmp[tmp["row"].isin(keep_rows)]
    if max_cols is not None and wells["col"].nunique() > max_cols:
        tmp = _renumber_and_label(wells)
        keep_cols = sorted(tmp["col"].unique())[:max_cols]
        info["capped_cols_kept"] = keep_cols
        info["capped_cols_total"] = int(tmp["col"].nunique())
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
      - "auto" (default): estimate rotation from data via a circular mean of
        NN-vector angles.
      - numeric: use the given rotation in DEGREES (positive = counter-clockwise
        in image coords). Use 0 to force pure axis-aligned behavior.

    The initial rotation + axis-aligned pitch fit only seeds the grid indices.
    It is then refined by a least-squares affine fit (x, y) ≈ [1, i, j] @ P on
    the snapped detections, re-snapped, up to MAX_REFIT_ITER times. The median
    pitch alone drifts by tens of px over a 25-row chip when the row spacing
    alternates (e.g. 148/156 px); the affine fit uses the mean period and also
    absorbs a slight shear between the row and column axes.
    """
    MAX_REFIT_ITER = 3
    MIN_REFIT_PAIRS = 6

    det_xy = centers[["x", "y"]].to_numpy(dtype=float)
    det_r = centers["r"].to_numpy(dtype=float)
    default_r = float(np.median(det_r))

    # --- determine rotation ---
    if isinstance(rotation_deg, str) and rotation_deg.lower() == "auto":
        theta = estimate_rotation(centers, k_nn=k_nn)
        rotation_source = "auto"
    else:
        theta = float(np.radians(float(rotation_deg)))
        rotation_source = "manual"

    # --- initial fit: de-rotate, axis-aligned pitches + origin, grid ---
    # Rotate around the centroid of detections so coordinates stay in roughly
    # the same range (avoids creating huge negative values).
    pivot = det_xy.mean(axis=0)
    pts_aa = _rotate_xy(det_xy, -theta, pivot)
    centers_aa = centers.copy()
    centers_aa["x"] = pts_aa[:, 0]
    centers_aa["y"] = pts_aa[:, 1]
    col_pitch, row_pitch = estimate_pitches(centers_aa, k_nn=k_nn, axis_band=axis_band)
    # Degenerate input (all detections in one row/col, or a single one): one
    # pitch is undefined. Borrow the other so the grid is still well formed.
    if not np.isfinite(col_pitch):
        col_pitch = row_pitch if np.isfinite(row_pitch) else 4.0 * default_r
    if not np.isfinite(row_pitch):
        row_pitch = col_pitch
    x0, y0 = estimate_origin(centers_aa, col_pitch, row_pitch)
    grid_pts = generate_grid(centers_aa, col_pitch, row_pitch, x0, y0)

    # Grid indices + predicted positions in the ORIGINAL image frame. The
    # first snap is done there too (rotation preserves distances).
    ij = np.array([(i, j) for (i, j, _, _) in grid_pts], dtype=int).reshape(-1, 2)
    gxy_aa = np.array([(gx, gy) for (_, _, gx, gy) in grid_pts], dtype=float).reshape(-1, 2)
    pred = _rotate_xy(gxy_aa, theta, pivot)
    assign = _assign_unique(pred, det_xy, snap_tolerance)

    # --- refit loop: affine LSQ on (i, j) <-> assigned detection ---
    refit_iterations = 0
    P = None
    for _ in range(MAX_REFIT_ITER):
        m = assign >= 0
        if m.sum() < MIN_REFIT_PAIRS:
            break
        X = np.column_stack([np.ones(m.sum()), ij[m]])
        if np.linalg.matrix_rank(X) < 3:
            break
        P_new, *_ = np.linalg.lstsq(X, det_xy[assign[m]], rcond=None)
        if abs(np.linalg.det(P_new[1:])) < 1e-9:
            break
        P = P_new
        refit_iterations += 1
        ij_new = _affine_grid(P, det_xy)
        pred_new = _affine_predict(P, ij_new)
        assign_new = _assign_unique(pred_new, det_xy, snap_tolerance)
        # Compare assignments as sets of (i, j, detection) triples; the grid
        # range itself may change between iterations.
        old = {(int(a), int(b), int(k)) for (a, b), k in zip(ij[m], assign[m])}
        mn = assign_new >= 0
        new = {(int(a), int(b), int(k)) for (a, b), k in zip(ij_new[mn], assign_new[mn])}
        ij, pred, assign = ij_new, pred_new, assign_new
        if new == old:
            break

    # --- rescue: unassigned grid points take the nearest unassigned
    # detection within default_r (greedy, unique) ---
    det_taken = np.zeros(len(det_xy), bool)
    det_taken[assign[assign >= 0]] = True
    rescue = _assign_unique(pred, det_xy, default_r,
                            grid_taken=assign >= 0, det_taken=det_taken)
    n_rescued_all = rescue >= 0
    assign = np.where(n_rescued_all, rescue, assign)

    # --- outputs: detected wells carry the exact Hough x, y, r ---
    if len(det_xy):
        nn_d, _ = cKDTree(det_xy).query(pred, k=1)
    else:
        nn_d = np.full(len(pred), np.inf)
    rows = []
    for g in range(len(ij)):
        k = assign[g]
        if k >= 0:
            d = float(np.hypot(*(pred[g] - det_xy[k])))
            rows.append((int(ij[g, 0]), int(ij[g, 1]),
                         centers["x"].iat[k], centers["y"].iat[k], centers["r"].iat[k],
                         "detected", d, bool(n_rescued_all[g])))
        else:
            rows.append((int(ij[g, 0]), int(ij[g, 1]),
                         float(pred[g, 0]), float(pred[g, 1]), default_r,
                         "filled", float(nn_d[g]), False))
    wells = pd.DataFrame(rows, columns=["row", "col", "x", "y", "r", "source",
                                        "dist_to_det", "_rescued"])

    n_before = len(wells)
    n_det_before = int((wells.source == "detected").sum())

    # --- trim ---
    wells, trim_info = trim_lattice(
        wells,
        min_detected_fraction=min_detected_fraction,
        max_rows=max_rows, max_cols=max_cols,
    )
    n_rescued = int(wells["_rescued"].sum()) if len(wells) else 0
    wells = wells.drop(columns="_rescued")

    resid = wells.loc[wells.source == "detected", "dist_to_det"].to_numpy(float)
    resid_median = float(np.median(resid)) if len(resid) else float("nan")
    resid_p95 = float(np.percentile(resid, 95)) if len(resid) else float("nan")

    # Report the refit geometry when there is one: a = row step, b = col step.
    if P is not None:
        a, b = P[1], P[2]
        col_pitch = float(np.hypot(*b))
        row_pitch = float(np.hypot(*a))
        rotation_deg_out = float(np.degrees(np.arctan2(b[1], b[0])))
    else:
        rotation_deg_out = float(np.degrees(theta))

    info = {
        "col_pitch": col_pitch, "row_pitch": row_pitch,
        "x0": x0, "y0": y0, "default_r": default_r,
        "rotation_deg": rotation_deg_out,
        "rotation_source": rotation_source,
        "n_grid": len(ij),
        "n_detected": int((wells.source == "detected").sum()),
        "n_filled": int((wells.source == "filled").sum()),
        "n_before_trim": n_before,
        "n_detected_before_trim": n_det_before,
        "n_trimmed": n_before - len(wells),
        "resid_median": resid_median,
        "resid_p95": resid_p95,
        "refit_iterations": refit_iterations,
        "n_rescued": n_rescued,
        **trim_info,
    }
    return wells, info
