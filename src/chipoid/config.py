"""Config loader: merge a user YAML config with built-in defaults, then validate.

Usage:
    from chipoid.config import load_config
    cfg = load_config(Path("configs/default.yaml"))
    cfg["readout"]["margin"]    # access via plain dict
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


DEFAULTS: dict[str, Any] = {
    "input": {
        # Path to the manifest CSV listing one image per row.
        "manifest": "configs/manifest.csv",
        # All manifest `source` paths are resolved relative to this root.
        "data_root": "data",
        # Whether to split a multi-page raw TIFF into one brightfield + one
        # companion per marker before processing.
        #   false: manifest `source` is the brightfield directly; companions
        #          are found by convention <stem>_<marker>.tif
        #   true:  manifest `source` is the multi-page raw; pages are split
        #          into output/<image_id>/<image_id>{,_<marker>}.tif
        #          (and optionally deleted after processing — see
        #          output.keep_extracted below).
        "extract_channels": {
            "enabled": False,
            # Page index per channel inside the raw multi-page TIFF. Must
            # include 'brightfield' AND every marker name listed in `markers`.
            "pages": {
                "brightfield": 0,
                # green: 1
                # red:   2
            },
        },
    },

    # Marker (fluorescence channel) names, in display order. Must match the
    # companion-file suffixes and the `pages` keys above when extracting.
    "markers": ["green", "red"],

    "detection": {
        "radius_min": 35,
        "radius_max": 50,
        "radius_step": 1,
        "canny_sigma": 2.0,
        # null -> skimage auto-thresholding (10% / 20% of dtype range).
        # NOTE: these defaults assume the brightfield is 8-bit. If you supply
        # a higher-bit-depth BF, you MUST set these manually (see README).
        "canny_low_threshold": None,
        "canny_high_threshold": None,
        "peak_threshold": 0.30,
        # Minimum pixel separation between accepted peaks. Set < well pitch but
        # > well diameter so we don't get duplicate detections inside one well.
        "min_spacing": 110,
        # Cap on peaks returned; well above any plausible per-image count.
        "max_peaks": 2000,
    },

    "lattice": {
        "enabled": True,
        # k-nearest-neighbors used to estimate row/col pitch from detections.
        "k_nn": 4,
        # When projecting NN vectors onto axes, keep only vectors with
        # |off-axis| <= axis_band as candidates for that axis.
        "axis_band": 50.0,
        # Max distance (px) a predicted grid point can be from a real detection
        # to count as "detected". Beyond this, the point is marked "filled".
        "snap_tolerance": 30.0,
        # Lattice rotation handling:
        #   "auto"  -> estimate rotation from data (robust circular median of
        #              NN-vector angles)
        #   numeric -> use this rotation in DEGREES (positive = CCW in image
        #              coords). Use 0 to force pure axis-aligned.
        "rotation_deg": "auto",
        # Density-filter threshold for trimming spurious rows/cols. After
        # snapping, any row (or col) where the fraction of Hough-detected
        # wells is below this is dropped entirely. Set to 0 to disable.
        # Default 0.25 = a row needs at least 1 detection out of 4 cols to survive.
        "min_detected_fraction": 0.25,
        # Optional hard caps on lattice dimensions. If set, the highest-index
        # rows/cols are trimmed until at most this many remain. Use only when
        # you know the chip's true layout and want a manual backstop.
        "max_rows": None,
        "max_cols": None,
    },

    "readout": {
        # Pixels to shrink the signal disk inward from r_well.
        "margin": 4.0,
        # Annulus inner/outer offset from r_well.
        "annulus_inner": 8.0,
        "annulus_outer": 20.0,
        # Which per-well, per-marker metrics to emit in the CSV.
        # Any subset of the supported set is allowed (see METRICS.md).
        "metrics": [
            "mean",
            "median",
            "std",
            "bg_median",
            "signal",         # mean - bg_median (primary readout)
            "signal_median",  # median - bg_median (robust alt)
            "n_signal_px",
            "n_bg_px",
            "partial_disk",
        ],
    },

    "output": {
        "dir": "output",
        # Per-image subdirectory? If true, each image's PNGs/CSV live in output/<image_id>/.
        # If false, files are written flat into output/ with image_id prefixes (one-image runs only).
        "per_image_subdir": True,
        # Combined per-image inspection figure (BF + lattice + intensities + scatter).
        "save_review_figure": True,
        # Individual stage overlays (canny, hough, lattice, intensity per marker).
        "save_stage_overlays": True,
        # Per-image scatter and histogram diagnostic PNGs.
        "save_diagnostics": True,
        # Filename of the consolidated CSV at the batch root.
        "consolidated_csv": "wells_all.csv",
        # One-row-per-image summary CSV at the batch root.
        "batch_summary_csv": "batch_summary.csv",
        # When extract_channels.enabled is true, the split BF + companion TIFFs
        # land in output/<image_id>/ alongside the overlays. Set this to false
        # to delete them after the per-image readout completes (saves disk if
        # you re-extract often and don't need the split files long-term).
        "keep_extracted": True,
    },
}


SUPPORTED_METRICS = {
    "mean", "median", "std", "bg_median", "signal", "signal_median",
    "n_signal_px", "n_bg_px", "partial_disk",
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base`. Lists and scalars are replaced."""
    out = deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load a YAML config and merge it on top of the built-in defaults.

    Passing `path=None` returns the defaults unchanged (useful for tests / dry runs).
    """
    cfg = deepcopy(DEFAULTS)
    if path is not None:
        with open(path) as f:
            user = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, user)
    _validate(cfg)
    return cfg


def _validate(cfg: dict[str, Any]) -> None:
    markers = cfg.get("markers") or []
    if not markers:
        raise ValueError("config.markers must be a non-empty list (e.g. ['green', 'red'])")

    metrics = cfg["readout"]["metrics"]
    bad = set(metrics) - SUPPORTED_METRICS
    if bad:
        raise ValueError(
            f"config.readout.metrics contains unknown metric(s): {sorted(bad)}. "
            f"Supported: {sorted(SUPPORTED_METRICS)}"
        )

    ex = cfg["input"]["extract_channels"]
    if ex.get("enabled"):
        pages = ex.get("pages") or {}
        if "brightfield" not in pages:
            raise ValueError("extract_channels.pages must include 'brightfield' page index")
        missing = [m for m in markers if m not in pages]
        if missing:
            raise ValueError(
                f"extract_channels.pages is missing entries for marker(s) {missing}; "
                f"every marker in `markers` needs a page index when extraction is enabled"
            )
