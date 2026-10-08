"""Validate a chipOid run against a baseline run and/or hand-picked wells.

Prints markdown tables (paste-ready for issues and handoff notes). All paths
are arguments; no data lives in the repo.

Usage:
    python scripts/validate_exp.py --run OUT_DIR [OUT_DIR ...]
        [--baseline OUT_DIR [OUT_DIR ...]]   # compare wells_all.csv well by well
        [--picks picks.csv]                  # columns: image_id, well_id (hand-picked wells)
        [--fraction green/red]               # per-well green / (green + red); default: first two markers
        [--thresholds 25,50,100,200]         # offline re-score: keep if max(signal_*) >= T

Each OUT_DIR is a chipOid output root (contains wells_all.csv, optionally
batch_summary.csv). Several dirs are concatenated, so per-condition runs work.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_COLS = {"image_id", "well_id", "row", "col", "x", "y", "r", "source", "dist_to_det",
               "included", "exclude_reason"}


def load_runs(dirs: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    wells = pd.concat([pd.read_csv(d / "wells_all.csv") for d in dirs], ignore_index=True)
    sums = [pd.read_csv(d / "batch_summary.csv") for d in dirs if (d / "batch_summary.csv").exists()]
    return wells, (pd.concat(sums, ignore_index=True) if sums else None)


def markers_of(wells: pd.DataFrame) -> list[str]:
    return [c[len("signal_"):] for c in wells.columns
            if c.startswith("signal_") and not c.startswith("signal_median_")]


def as_bool(s: pd.Series) -> np.ndarray:
    return s.astype(str).str.lower().isin(["true", "1"]).to_numpy()


def frac_stats(df: pd.DataFrame, num: str, other: str) -> str:
    if len(df) == 0:
        return "0 / – / –"
    g = df[f"signal_{num}"].to_numpy(float)
    r = df[f"signal_{other}"].to_numpy(float)
    per_well = np.nanmean(g / (g + r)) * 100
    pooled = np.nansum(g) / (np.nansum(g) + np.nansum(r)) * 100
    return f"{len(df)} / {per_well:.1f} / {pooled:.1f}"


def keep_mask(df: pd.DataFrame, markers: list[str], t: float) -> np.ndarray:
    sig = np.column_stack([df[f"signal_{m}"].to_numpy(float) for m in markers])
    return np.nanmax(np.where(np.isnan(sig), -np.inf, sig), axis=1) >= t


def section_geometry(wells, summary):
    print("## Geometry\n")
    print("| image | wells | detected | filled | r_well | residual median / p95 / max (px) |")
    print("|---|---|---|---|---|---|")
    for img, df in wells.groupby("image_id", sort=False):
        det = df[df.source == "detected"].dist_to_det
        r_well = (summary.set_index("image_id").loc[img, "median_radius"]
                  if summary is not None and "median_radius" in summary else df.r.median())
        print(f"| {img} | {len(df)} | {len(det)} | {len(df) - len(det)} | {r_well:.0f} | "
              f"{det.median():.1f} / {np.percentile(det, 95):.1f} / {det.max():.1f} |")
    print()


def section_baseline(wells, base):
    print("## Comparison with baseline\n")
    only_run = sorted(set(wells.columns) - set(base.columns))
    only_base = sorted(set(base.columns) - set(wells.columns))
    print(f"Columns only in run: {only_run or 'none'} · only in baseline: {only_base or 'none'}\n")
    metric_cols = [c for c in wells.columns if c in base.columns and c not in SOURCE_COLS
                   and pd.api.types.is_numeric_dtype(base[c]) and base[c].dtype != bool]
    print("| image | wells (run/base) | source changed | max abs dx, dy (px) | wells with any metric change | max abs d signal_* |")
    print("|---|---|---|---|---|---|")
    for img, df in wells.groupby("image_id", sort=False):
        b = base[base.image_id == img]
        m = df.merge(b, on="well_id", suffixes=("", "_b"))
        src = sorted(m.well_id[m.source != m.source_b])
        dx = np.abs(m.x - m.x_b).max(); dy = np.abs(m.y - m.y_b).max()
        changed = np.zeros(len(m), bool)
        for c in metric_cols:
            changed |= ~np.isclose(m[c].to_numpy(float), m[f"{c}_b"].to_numpy(float),
                                   rtol=0, atol=1e-9, equal_nan=True)
        dsig = max((np.nanmax(np.abs(m[c] - m[f"{c}_b"])) for c in metric_cols
                    if c.startswith("signal_")), default=0.0)
        print(f"| {img} | {len(df)}/{len(b)} | {', '.join(src) or 'none'} | {dx:.3g}, {dy:.3g} | "
              f"{int(changed.sum())} | {dsig:.3g} |")
    print()


def section_fractions(wells, num, other, thresholds, markers):
    has_incl = "included" in wells.columns
    head = ["image", "all wells"] + (["included (run)"] if has_incl else []) + [f"T = {t:g}" for t in thresholds]
    print(f"## {num} fraction, n / mean of per-well % / pooled Σ %\n")
    print(f"Offline re-score keeps a well if max(signal_*) ≥ T over markers {markers}.\n")
    print("| " + " | ".join(head) + " |"); print("|" + "---|" * len(head))
    for img, df in wells.groupby("image_id", sort=False):
        cells = [img, frac_stats(df, num, other)]
        if has_incl:
            cells.append(frac_stats(df[as_bool(df.included)], num, other))
        cells += [frac_stats(df[keep_mask(df, markers, t)], num, other) for t in thresholds]
        print("| " + " | ".join(cells) + " |")
    print()


def section_picks(wells, picks, thresholds, markers):
    print("## Agreement with hand-picked wells\n")
    print("| image | picks | rule | agree | kept but not picked | picked but not kept |")
    print("|---|---|---|---|---|---|")
    for img, p in picks.groupby("image_id", sort=False):
        df = wells[wells.image_id == img]
        if df.empty:
            continue
        sel = df.well_id.isin(set(p.well_id)).to_numpy()
        rules = ([("included (run)", as_bool(df.included))] if "included" in df.columns else [])
        rules += [(f"max ≥ {t:g}", keep_mask(df, markers, t)) for t in thresholds]
        for name, keep in rules:
            extra = sorted(df.well_id[keep & ~sel]); missing = sorted(df.well_id[~keep & sel])
            print(f"| {img} | {sel.sum()} | {name} | {(keep == sel).sum()}/{len(df)} | "
                  f"{', '.join(extra) or '–'} | {', '.join(missing) or '–'} |")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", nargs="+", type=Path, required=True)
    ap.add_argument("--baseline", nargs="+", type=Path)
    ap.add_argument("--picks", type=Path)
    ap.add_argument("--fraction", help="NUM/OTHER marker names, e.g. green/red")
    ap.add_argument("--thresholds", default="25,50,100,200")
    a = ap.parse_args()

    wells, summary = load_runs(a.run)
    markers = markers_of(wells)
    thresholds = [float(t) for t in a.thresholds.split(",") if t.strip()]
    section_geometry(wells, summary)
    if a.baseline:
        section_baseline(wells, load_runs(a.baseline)[0])
    if len(markers) >= 2:
        num, other = a.fraction.split("/") if a.fraction else markers[:2]
        section_fractions(wells, num, other, thresholds, markers)
    if a.picks:
        section_picks(wells, pd.read_csv(a.picks), thresholds, markers)


if __name__ == "__main__":
    main()
