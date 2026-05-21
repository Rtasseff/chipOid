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
                           cmap="viridis", label_wells: bool = True):
    """BF with FILLED transparent disks colored by per-well metric values.

    Filled (not just outlined) so magnitude is readable across many wells.
    Alpha keeps the BF visible underneath for context."""
    vmin, vmax = _color_scale(values)
    fig, ax = plt.subplots(figsize=_figsize_for(bf.shape))
    ax.imshow(bf, cmap="gray", interpolation="nearest")
    norm = plt.Normalize(vmin=vmin, vmax=vmax); cm = plt.get_cmap(cmap)
    for (_, w), v in zip(wells.iterrows(), values):
        color = "red" if not np.isfinite(v) else cm(norm(v))
        # Filled, semi-transparent disk inside the well; thin matching edge.
        ax.add_patch(mpatches.Circle(
            (w.x, w.y), w.r,
            facecolor=color, edgecolor=color, lw=0.5,
            alpha=INTENSITY_ALPHA,
        ))
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


def save_scatter(wells, x_col, y_col, x_label, y_label, out_path):
    """Generic per-well scatter (two markers)."""
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(wells[x_col], wells[y_col], c="steelblue", s=22,
               edgecolor="k", linewidth=0.3)
    ax.set_xlabel(x_label); ax.set_ylabel(y_label); ax.set_title("per-well fluorescence")
    plt.tight_layout(); plt.savefig(out_path, dpi=130); plt.close(fig)


# --------------------------------------------------------------------------- #
# Composite review figure (one per image)
# --------------------------------------------------------------------------- #
def save_review_figure(bf, wells, marker_signals, out_path,
                       image_id: str, lattice_info: dict, n_hough: int):
    """Combined per-image figure for batch review.

    Layout (left to right):
      [BF + lattice overlay] [BF + marker-A signal] ... [BF + marker-N signal]
      [scatter (if 2+ markers)] [histograms]
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
    ax.set_title(f"{image_id}\nlattice {lattice_info['n_detected']}/{n_hough} det "
                 f"({lattice_info['col_pitch']:.0f}×{lattice_info['row_pitch']:.0f})",
                 fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])

    # Per-marker intensity panels (filled disks for at-a-glance magnitude)
    for marker, vals in marker_signals.items():
        ax = fig.add_subplot(gs[0, col]); col += 1
        ax.imshow(bf, cmap="gray", interpolation="nearest")
        vmin, vmax = _color_scale(vals)
        norm = plt.Normalize(vmin=vmin, vmax=vmax); cm = plt.get_cmap("viridis")
        for (_, w), v in zip(wells.iterrows(), vals):
            color = "red" if not np.isfinite(v) else cm(norm(v))
            ax.add_patch(mpatches.Circle(
                (w.x, w.y), w.r,
                facecolor=color, edgecolor=color, lw=0.4,
                alpha=INTENSITY_ALPHA,
            ))
        ax.set_title(f"{marker} signal\n[{vmin:.0f}, {vmax:.0f}]", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])

    if have_scatter:
        ax = fig.add_subplot(gs[0, col]); col += 1
        m1, m2 = marker_names[:2]
        ax.scatter(marker_signals[m1], marker_signals[m2],
                   c="steelblue", s=20, edgecolor="k", linewidth=0.3)
        ax.set_xlabel(m1); ax.set_ylabel(m2); ax.set_title("per-well fluorescence", fontsize=9)

    ax = fig.add_subplot(gs[0, col])
    for marker, vals in marker_signals.items():
        finite = vals[np.isfinite(vals)]
        ax.hist(finite, bins=20, alpha=0.5, label=marker)
    ax.set_xlabel("signal"); ax.set_ylabel("wells"); ax.set_title("distributions", fontsize=9)
    ax.legend(fontsize=8)

    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
