"""All overlay/figure rendering. Keeping these together makes styling consistent
across stages and lets the review composite reuse the same primitives.

Style guide:
  - Lattice / Hough overlays use OPEN circles (border only). The purpose is to
    show where wells are located, not to obscure them.
  - Intensity overlays use FILLED, semi-transparent disks colored by the metric.
    Filled disks make magnitude readable at-a-glance across hundreds of wells.
  - Where useful, wells are labeled with their `well_id` (e.g. "r05c02") so
    visual inspection cross-references directly to a row in wells.csv.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.patheffects as mpe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# Filled intensity disks are drawn at this alpha. High enough to see the color
# clearly, low enough that the BF underneath is still visible for context.
INTENSITY_ALPHA = 0.55

# Well-label font size for at-pixel overlays. Tuned for our typical ~84 px
# well diameter at dpi=130.
LABEL_FONTSIZE = 5
LABEL_COLOR = "white"

# Wells excluded by the inclusion step are drawn grey (fill) with a dashed edge
# instead of a colormap colour; included wells are steelblue in scatters.
EXCLUDED_FILL = "#bdbdbd"
EXCLUDED_EDGE = "#757575"
INCLUDED_COLOR = "steelblue"


def _add_intensity_disk(ax, w, v, norm, cm, excluded: bool, lw: float):
    """One filled intensity disk; grey with a dashed edge when excluded."""
    if excluded:
        ax.add_patch(mpatches.Circle(
            (w.x, w.y), w.r, facecolor=EXCLUDED_FILL, edgecolor=EXCLUDED_EDGE,
            lw=lw, ls="--", alpha=INTENSITY_ALPHA,
        ))
        return
    color = "red" if not np.isfinite(v) else cm(norm(v))
    ax.add_patch(mpatches.Circle(
        (w.x, w.y), w.r, facecolor=color, edgecolor=color, lw=lw,
        alpha=INTENSITY_ALPHA,
    ))


def _draw_inclusion_scatter(ax, x, y, included, thresholds, s, label_fontsize=8):
    """Scatter coloured by inclusion, with dashed threshold lines and a legend."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    inc = np.asarray(included, bool)
    ax.scatter(x[~inc], y[~inc], c=EXCLUDED_FILL, s=s, edgecolor="k", linewidth=0.3,
               label=f"excluded ({int((~inc).sum())})")
    ax.scatter(x[inc], y[inc], c=INCLUDED_COLOR, s=s, edgecolor="k", linewidth=0.3,
               label=f"included ({int(inc.sum())})")
    if thresholds is not None:
        ax.axvline(thresholds[0], color="grey", ls="--", lw=0.9)
        ax.axhline(thresholds[1], color="grey", ls="--", lw=0.9)
    ax.legend(fontsize=label_fontsize)


def _figsize_for(img_shape, base=8):
    H, W = img_shape
    return (base, max(6, H / W * base))


def _label_well(ax, x, y, label):
    """Small text label centered on a well. White with a thin black halo so it
    reads against any background color underneath."""
    txt = ax.text(x, y, label, fontsize=LABEL_FONTSIZE, color=LABEL_COLOR,
                  ha="center", va="center", weight="bold")
    # Thin black outline for legibility on light backgrounds.
    txt.set_path_effects([mpe.withStroke(linewidth=0.8, foreground="black")])


# --------------------------------------------------------------------------- #
# Stage overlays
# --------------------------------------------------------------------------- #
def save_canny(edges: np.ndarray, out_path: Path, canny_sigma: float):
    fig, ax = plt.subplots(figsize=_figsize_for(edges.shape))
    ax.imshow(edges, cmap="gray", interpolation="nearest")
    ax.set_title(f"Canny edges (sigma={canny_sigma})")
    plt.tight_layout(); plt.savefig(out_path, dpi=120); plt.close(fig)


def save_hough_overlay(bf: np.ndarray, centers: pd.DataFrame, out_path: Path,
                       radius_range: tuple[int, int]):
    fig, ax = plt.subplots(figsize=_figsize_for(bf.shape))
    ax.imshow(bf, cmap="gray", interpolation="nearest")
    # Open circles: purpose is to show DETECTED LOCATIONS, not magnitudes.
    for _, row in centers.iterrows():
        ax.add_patch(mpatches.Circle((row.x, row.y), row.r, fill=False, ec="lime", lw=0.6))
        ax.plot(row.x, row.y, "r.", ms=1.5)
    ax.set_title(f"Hough: {len(centers)} centers, r in {radius_range}")
    plt.tight_layout(); plt.savefig(out_path, dpi=130); plt.close(fig)


def save_lattice_overlay(bf: np.ndarray, wells: pd.DataFrame, out_path: Path,
                         info: dict, label_wells: bool = True):
    fig, ax = plt.subplots(figsize=_figsize_for(bf.shape))
    ax.imshow(bf, cmap="gray", interpolation="nearest")
    for _, w in wells.iterrows():
        # Open circles: this overlay is about geometry/source, not intensity.
        # Color encodes source (lime=Hough-detected, magenta=lattice-filled).
        ec = "lime" if w.source == "detected" else "magenta"
        ls = "-" if w.source == "detected" else "--"
        a = 0.85 if w.source == "detected" else 0.6
        ax.add_patch(mpatches.Circle((w.x, w.y), w.r, fill=False, ec=ec, lw=0.7, ls=ls, alpha=a))
        if label_wells and "well_id" in w:
            _label_well(ax, w.x, w.y, w["well_id"])
    handles = [
        mpatches.Patch(edgecolor="lime", facecolor="none", label="detected"),
        mpatches.Patch(edgecolor="magenta", facecolor="none", label="filled"),
    ]
    ax.legend(handles=handles, loc="lower right", framealpha=0.9, fontsize=8)
    ax.set_title(
        f"Lattice: {info['n_detected']} detected + {info['n_filled']} filled "
        f"(col={info['col_pitch']:.0f}, row={info['row_pitch']:.0f})"
    )
    plt.tight_layout(); plt.savefig(out_path, dpi=130); plt.close(fig)


def _color_scale(values: np.ndarray):
    finite = np.isfinite(values)
    if not finite.any():
        return 0.0, 1.0
    vmin = float(np.percentile(values[finite], 5))
    vmax = float(np.percentile(values[finite], 95))
    if vmax <= vmin:
        vmax = vmin + 1.0
    return vmin, vmax


def save_intensity_overlay(bf, wells, values, out_path, title, label,
                           cmap="viridis", label_wells: bool = True,
                           included=None):
    """BF with FILLED transparent disks colored by per-well metric values.

    Filled (not just outlined) so magnitude is readable across many wells.
    Alpha keeps the BF visible underneath for context. `included` (bool array,
    optional) draws excluded wells grey with a dashed edge; the colour scale
    is unaffected."""
    vmin, vmax = _color_scale(values)
    fig, ax = plt.subplots(figsize=_figsize_for(bf.shape))
    ax.imshow(bf, cmap="gray", interpolation="nearest")
    norm = plt.Normalize(vmin=vmin, vmax=vmax); cm = plt.get_cmap(cmap)
    excl = np.zeros(len(wells), bool) if included is None else ~np.asarray(included, bool)
    for (_, w), v, ex in zip(wells.iterrows(), values, excl):
        # Filled, semi-transparent disk inside the well; thin matching edge.
        _add_intensity_disk(ax, w, v, norm, cm, ex, lw=0.5)
        if label_wells and "well_id" in w:
            _label_well(ax, w.x, w.y, w["well_id"])
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cm); sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax, fraction=0.025, pad=0.02); cbar.set_label(label)
    ax.set_title(title)
    plt.tight_layout(); plt.savefig(out_path, dpi=130); plt.close(fig)


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
def save_histograms(wells, signal_columns, out_path):
    """One subplot per marker. `signal_columns` is dict marker->column name."""
    n = len(signal_columns)
    fig, axes = plt.subplots(1, n, figsize=(5.5 * n, 4), squeeze=False)
    axes = axes[0]
    for ax, (marker, col) in zip(axes, signal_columns.items()):
        vals = wells[col].dropna().to_numpy()
        ax.hist(vals, bins=30, alpha=0.75)
        ax.set_xlabel("signal (mean - bg)"); ax.set_ylabel("wells")
        ax.set_title(marker)
    plt.tight_layout(); plt.savefig(out_path, dpi=130); plt.close(fig)


def save_scatter(wells, x_col, y_col, x_label, y_label, out_path,
                 included=None, thresholds=None):
    """Generic per-well scatter (two markers).

    `included` (bool array) colours included wells steelblue and excluded wells
    grey; `thresholds` = (x_threshold, y_threshold) adds dashed grey lines."""
    fig, ax = plt.subplots(figsize=(6, 6))
    if included is None:
        ax.scatter(wells[x_col], wells[y_col], c=INCLUDED_COLOR, s=22,
                   edgecolor="k", linewidth=0.3)
    else:
        _draw_inclusion_scatter(ax, wells[x_col], wells[y_col], included, thresholds, s=22)
    ax.set_xlabel(x_label); ax.set_ylabel(y_label); ax.set_title("per-well fluorescence")
    plt.tight_layout(); plt.savefig(out_path, dpi=130); plt.close(fig)


# --------------------------------------------------------------------------- #
# Composite review figure (one per image)
# --------------------------------------------------------------------------- #
def save_review_figure(bf, wells, marker_signals, out_path,
                       image_id: str, lattice_info: dict, n_hough: int,
                       included=None, scatter_signals=None, thresholds=None,
                       scatter_metric: str = "signal"):
    """Combined per-image figure for batch review.

    Layout (left to right):
      [BF + lattice overlay] [BF + marker-A signal] ... [BF + marker-N signal]
      [scatter (if 2+ markers)] [histograms]

    Inclusion marking (all optional; None = unchanged output): `included` greys
    out excluded wells in the intensity panels and the scatter; `thresholds`
    ({marker: T}) draws the scatter threshold lines; `scatter_signals`
    ({marker: array}) overrides the scatter values (the metric the thresholds
    apply to, labelled `scatter_metric`).
    """
    marker_names = list(marker_signals.keys())
    n_overlays = 1 + len(marker_names)
    have_scatter = len(marker_names) >= 2
    n_panels = n_overlays + (1 if have_scatter else 0) + 1

    H, W = bf.shape
    panel_w = 3.6
    panel_h = max(5, H / W * panel_w)
    fig = plt.figure(figsize=(panel_w * n_panels, panel_h))
    gs = fig.add_gridspec(1, n_panels, wspace=0.05)
    col = 0

    # Lattice (open circles; labels omitted at this scale — too small to read)
    ax = fig.add_subplot(gs[0, col]); col += 1
    ax.imshow(bf, cmap="gray", interpolation="nearest")
    for _, w in wells.iterrows():
        ec = "lime" if w.source == "detected" else "magenta"
        ax.add_patch(mpatches.Circle((w.x, w.y), w.r, fill=False, ec=ec, lw=0.7,
                                     ls="-" if w.source == "detected" else "--"))
    n_inc = "" if included is None else f" · {int(np.sum(included))} included"
    ax.set_title(f"{image_id}\nlattice {lattice_info['n_detected']}/{n_hough} det "
                 f"({lattice_info['col_pitch']:.0f}×{lattice_info['row_pitch']:.0f})"
                 f"{n_inc}",
                 fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])

    # Per-marker intensity panels (filled disks for at-a-glance magnitude)
    excl = np.zeros(len(wells), bool) if included is None else ~np.asarray(included, bool)
    for marker, vals in marker_signals.items():
        ax = fig.add_subplot(gs[0, col]); col += 1
        ax.imshow(bf, cmap="gray", interpolation="nearest")
        vmin, vmax = _color_scale(vals)
        norm = plt.Normalize(vmin=vmin, vmax=vmax); cm = plt.get_cmap("viridis")
        for (_, w), v, ex in zip(wells.iterrows(), vals, excl):
            _add_intensity_disk(ax, w, v, norm, cm, ex, lw=0.4)
        ax.set_title(f"{marker} signal\n[{vmin:.0f}, {vmax:.0f}]", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])

    if have_scatter:
        ax = fig.add_subplot(gs[0, col]); col += 1
        m1, m2 = marker_names[:2]
        sv = scatter_signals if scatter_signals is not None else marker_signals
        if included is None:
            ax.scatter(sv[m1], sv[m2], c=INCLUDED_COLOR, s=20, edgecolor="k", linewidth=0.3)
            ax.set_xlabel(m1); ax.set_ylabel(m2)
        else:
            t = None if thresholds is None else (thresholds[m1], thresholds[m2])
            _draw_inclusion_scatter(ax, sv[m1], sv[m2], included, t, s=20, label_fontsize=7)
            ax.set_xlabel(f"{m1} {scatter_metric}"); ax.set_ylabel(f"{m2} {scatter_metric}")
        ax.set_title("per-well fluorescence", fontsize=9)

    ax = fig.add_subplot(gs[0, col])
    for marker, vals in marker_signals.items():
        finite = vals[np.isfinite(vals)]
        ax.hist(finite, bins=20, alpha=0.5, label=marker)
    ax.set_xlabel("signal"); ax.set_ylabel("wells"); ax.set_title("distributions", fontsize=9)
    ax.legend(fontsize=8)

    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
