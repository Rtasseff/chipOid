"""Synthetic tests for the lattice fit (no image I/O).

The main fixture mimics the EXP24 chips that broke v0.9 (issue #3): 25 rows x
4 cols, row spacing alternating 148/156 px, column pitch ~205 px, column axis
rotated ~0.7 deg and row axis ~0.9 deg (slight shear), 1 px jitter.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from chipoid.lattice import fit_lattice

IMAGE_SHAPE = (4200, 1200)
FIT_KW = dict(k_nn=4, axis_band=50.0, snap_tolerance=30.0, rotation_deg="auto",
              min_detected_fraction=0.25, max_rows=25, max_cols=4)


def make_chip(n_rows=25, n_cols=4, seed=0, jitter=1.0):
    """Return (truth, centers): truth has row/col/x/y for every well."""
    rng = np.random.default_rng(seed)
    col_ang = np.radians(0.7)
    row_ang = np.radians(0.9)
    b_dir = np.array([np.cos(col_ang), np.sin(col_ang)])    # column step direction
    a_dir = np.array([-np.sin(row_ang), np.cos(row_ang)])   # row step direction
    origin = np.array([220.0, 130.0])
    # cumulative row offsets: 148, 156, 148, 156, ...
    steps = np.array([148.0 if k % 2 == 0 else 156.0 for k in range(n_rows - 1)])
    row_off = np.concatenate([[0.0], np.cumsum(steps)])
    rows = []
    for i in range(n_rows):
        for j in range(n_cols):
            xy = origin + row_off[i] * a_dir + j * 205.0 * b_dir
            rows.append((i, j, xy[0], xy[1]))
    truth = pd.DataFrame(rows, columns=["row", "col", "x", "y"])
    centers = truth[["x", "y"]].copy()
    centers["x"] = np.round(centers["x"] + rng.normal(0, jitter, len(centers)))
    centers["y"] = np.round(centers["y"] + rng.normal(0, jitter, len(centers)))
    centers["r"] = np.where(np.arange(len(centers)) % 2 == 0, 38.0, 44.0)
    return truth, centers.reset_index(drop=True)


def _merge(wells, truth):
    return wells.merge(truth, on=["row", "col"], suffixes=("", "_true"))


def test_alternating_rows_dropped_detections_regression():
    truth, centers = make_chip()
    # drop 3 detections in the top rows (rows 0, 1, 2)
    drop = truth.index[(truth.row <= 2) & (truth.col == np.array([1, 2, 3])[truth.row.clip(0, 2)])]
    assert len(drop) == 3
    wells, info = fit_lattice(centers.drop(index=drop), IMAGE_SHAPE, **FIT_KW)

    assert len(wells) == 100
    assert (wells.source == "filled").sum() == 3
    assert (wells.source == "detected").sum() == 97
    m = _merge(wells, truth)
    filled = m[m.source == "filled"]
    err = np.hypot(filled.x - filled.x_true, filled.y - filled.y_true)
    assert (err < 3.0).all(), err.tolist()
    # the filled wells are the ones we dropped
    dropped_rc = set(map(tuple, truth.loc[drop, ["row", "col"]].to_numpy()))
    assert set(map(tuple, filled[["row", "col"]].to_numpy())) == dropped_rc
    assert info["resid_median"] < 3.0
    assert info["refit_iterations"] >= 1
    assert info["n_rescued"] == 0
    # refit geometry: mean row period ~152 px, col pitch ~205 px
    assert abs(info["row_pitch"] - 152.0) < 1.0
    assert abs(info["col_pitch"] - 205.0) < 1.0
    assert abs(info["rotation_deg"] - 0.7) < 0.2


def test_detected_wells_carry_exact_hough_values():
    _, centers = make_chip(seed=1)
    centers = centers.copy()
    # non-integer coordinates that would not survive a rotate/de-rotate trip
    centers["x"] = centers["x"] + 0.1
    centers["y"] = centers["y"] + 0.3
    wells, _ = fit_lattice(centers, IMAGE_SHAPE, **FIT_KW)
    det = wells[wells.source == "detected"]
    assert len(det) == 100
    hough = {(x, y, r) for x, y, r in centers[["x", "y", "r"]].itertuples(index=False)}
    for x, y, r in det[["x", "y", "r"]].itertuples(index=False):
        assert (x, y, r) in hough  # exact ==, not approx


def test_unique_assignment():
    # tight pitch 50 px with tolerance 30: a detection halfway between two
    # grid points is within tolerance of both.
    pts = [(100.0 + 50 * j, 100.0 + 50 * i) for i in range(4) for j in range(4)]
    centers = pd.DataFrame(pts, columns=["x", "y"])
    centers["r"] = 15.0
    # remove (row 1, col 1) and (row 1, col 2); add one detection midway
    centers = centers[~((centers.y == 150.0) & centers.x.isin([150.0, 200.0]))]
    centers = pd.concat([centers, pd.DataFrame({"x": [175.0], "y": [150.0], "r": [15.0]})],
                        ignore_index=True)
    wells, info = fit_lattice(centers, (400, 400), k_nn=4, axis_band=20.0,
                              snap_tolerance=30.0, rotation_deg=0.0,
                              min_detected_fraction=0.25)
    hit = wells[(wells.x == 175.0) & (wells.y == 150.0) & (wells.source == "detected")]
    assert len(hit) == 1
    # every detection is used at most once
    det = wells[wells.source == "detected"]
    assert not det.duplicated(subset=["x", "y"]).any()
    assert len(wells) == 16


def test_spurious_row_above_chip_is_trimmed():
    truth, centers = make_chip(seed=2)
    # a printed row label one row above the chip, beside column 0 (not on a
    # grid point, as on EXP24 TX100)
    label = pd.DataFrame({"x": [220.0 + 150 * np.sin(np.radians(0.9)) - 60.0],
                          "y": [130.0 - 150.0], "r": [40.0]})
    wells, info = fit_lattice(pd.concat([centers, label], ignore_index=True),
                              IMAGE_SHAPE, **FIT_KW)
    assert len(wells) == 100
    assert (wells.source == "detected").sum() == 100
    assert info["n_trimmed"] > 0
    assert not ((wells.x == label.x[0]) & (wells.y == label.y[0])).any()
    m = _merge(wells, truth)
    assert np.hypot(m.x - m.x_true, m.y - m.y_true).max() < 5.0


def test_perfect_axis_aligned_lattice_unchanged():
    pts = [(100.0 + 200 * j, 80.0 + 150 * i, 40.0) for i in range(10) for j in range(4)]
    centers = pd.DataFrame(pts, columns=["x", "y", "r"])
    wells, info = fit_lattice(centers, (1700, 1000), k_nn=4, axis_band=50.0,
                              snap_tolerance=30.0, rotation_deg="auto",
                              min_detected_fraction=0.25)
    assert len(wells) == 40
    assert (wells.source == "detected").all()
    assert info["resid_median"] < 1e-6
    for _, w in wells.iterrows():
        assert w.well_id == f"r{int(w.row):02d}c{int(w.col):02d}"
        assert w.x == 100.0 + 200 * w.col
        assert w.y == 80.0 + 150 * w.row
    assert abs(info["row_pitch"] - 150.0) < 1e-6
    assert abs(info["col_pitch"] - 200.0) < 1e-6


def test_degenerate_inputs_do_not_crash():
    few = pd.DataFrame({"x": [100.0, 300.0, 100.0, 300.0, 500.0],
                        "y": [100.0, 100.0, 250.0, 250.0, 100.0],
                        "r": [40.0] * 5})
    wells, info = fit_lattice(few, (600, 700), **{**FIT_KW, "max_rows": None, "max_cols": None})
    assert info["refit_iterations"] == 0
    assert (wells.source == "detected").sum() == 5

    one_row = pd.DataFrame({"x": [100.0 + 200 * j for j in range(8)],
                            "y": [100.0] * 8, "r": [40.0] * 8})
    wells, info = fit_lattice(one_row, (300, 1800), **{**FIT_KW, "max_rows": None, "max_cols": None})
    assert info["refit_iterations"] == 0
    assert set(wells.source) <= {"detected", "filled"}


def test_caps_trim_and_log_totals():
    # Both caps firing used to crash on a duplicate well_id insert.
    _, centers = make_chip(seed=3)
    wells, info = fit_lattice(centers, IMAGE_SHAPE,
                              **{**FIT_KW, "max_rows": 20, "max_cols": 3})
    assert len(wells) == 60
    assert len(info["capped_rows_kept"]) == 20 and info["capped_rows_total"] == 25
    assert len(info["capped_cols_kept"]) == 3 and info["capped_cols_total"] == 4
    assert wells.well_id.is_unique
