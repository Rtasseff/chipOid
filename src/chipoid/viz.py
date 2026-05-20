"""All overlay/figure rendering. Keeping these together makes styling consistent
across stages and lets the review composite reuse the same primitives.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _figsize_for(img_shape, base=8):
    H, W = img_shape
    return (base, max(6, H / W * base))


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
    for _, row in centers.iterrows():
        ax.add_patch(mpatches.Circle((row.x, row.y), row.r, fill=False, ec="lime", lw=0.6))
        ax.plot(row.x, row.y, "r.", ms=1.5)
    ax.set_title(f"Hough: {len(centers)} centers, r in {radius_range}")
    plt.tight_layout(); plt.savefig(out_path, dpi=130); plt.close(fig)


def save_lattice_overlay(bf: np.ndarray, wells: pd.DataFrame, out_path: Path,
                         info: dict):
    fig, ax = plt.subplots(figsize=_figsize_for(bf.shape))
    ax.imshow(bf, cmap="gray", interpolation="nearest")
    for _, w in wells.iterrows():
        ec = "lime" if w.source == "detected" else "magenta"
        ls = "-" if w.source == "detected" else "--"
        a = 0.85 if w.source == "detected" else 0.6
        ax.add_patch(mpatches.Circle((w.x, w.y), w.r, fill=False, ec=ec, lw=0.7, ls=ls, alpha=a))
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
                           cmap="viridis"):
    vmin, vmax = _color_scale(values)
    fig, ax = plt.subplots(figsize=_figsize_for(bf.shape))
    ax.imshow(bf, cmap="gray", interpolation="nearest")
    norm = plt.Normalize(vmin=vmin, vmax=vmax); cm = plt.get_cmap(cmap)
    for (_, w), v in zip(wells.iterrows(), values):
        color = "red" if not np.isfinite(v) else cm(norm(v))
        ax.add_patch(mpatches.Circle((w.x, w.y), w.r, fill=False, ec=color, lw=1.0))
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
    """Generic per-well scatter (two markers, no class coloring)."""
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

    `marker_signals`: dict marker -> 1-D array of signal values aligned with wells.
    """
    marker_names = list(marker_signals.keys())
    n_overlays = 1 + len(marker_names)  # lattice + each marker
    have_scatter = len(marker_names) >= 2
    n_panels = n_overlays + (1 if have_scatter else 0) + 1  # +1 for histograms

    H, W = bf.shape
    panel_w = 3.6
    panel_h = max(5, H / W * panel_w)
    fig = plt.figure(figsize=(panel_w * n_panels, panel_h))
    gs = fig.add_gridspec(1, n_panels, wspace=0.05)
    col = 0

    # Lattice
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

    # Per-marker intensity
    for marker, vals in marker_signals.items():
        ax = fig.add_subplot(gs[0, col]); col += 1
        ax.imshow(bf, cmap="gray", interpolation="nearest")
        vmin, vmax = _color_scale(vals)
        norm = plt.Normalize(vmin=vmin, vmax=vmax); cm = plt.get_cmap("viridis")
        for (_, w), v in zip(wells.iterrows(), vals):
            color = "red" if not np.isfinite(v) else cm(norm(v))
            ax.add_patch(mpatches.Circle((w.x, w.y), w.r, fill=False, ec=color, lw=1.0))
        ax.set_title(f"{marker} signal\n[{vmin:.0f}, {vmax:.0f}]", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])

    # Scatter (only if 2+ markers)
    if have_scatter:
        ax = fig.add_subplot(gs[0, col]); col += 1
        m1, m2 = marker_names[:2]
        v1 = marker_signals[m1]; v2 = marker_signals[m2]
        ax.scatter(v1, v2, c="steelblue", s=20, edgecolor="k", linewidth=0.3)
        ax.set_xlabel(m1); ax.set_ylabel(m2); ax.set_title("per-well fluorescence", fontsize=9)

    # Histograms
    ax = fig.add_subplot(gs[0, col])
    for marker, vals in marker_signals.items():
        finite = vals[np.isfinite(vals)]
        ax.hist(finite, bins=20, alpha=0.5, label=marker)
    ax.set_xlabel("signal"); ax.set_ylabel("wells"); ax.set_title("distributions", fontsize=9)
    ax.legend(fontsize=8)

    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
