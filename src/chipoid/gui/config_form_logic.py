"""Pure (non-Tk) logic for the chipOid config form.

`coerce_raw_values` takes a dict of stringly-typed widget values (the form
state at Run time) and returns a validated config dict that matches the
schema in `chipoid.config.DEFAULTS`. Splitting this out from `config_form.py`
lets us unit-test the validation/coercion rules without spinning up Tk —
useful because CI is headless.

The form widgets always store their state as strings (or `bool` for
Checkbutton), so coercion handles:
  - Numeric strings → int / float, blank → None (where applicable).
  - rotation_deg: "auto" stays string; anything else parses to float.
  - Comma-separated entries → list[str].
  - Metric checkboxes → list[str] of enabled metrics.
  - Filename schema fields are NOT in the cfg dict — they're a separate
    concern handled by the manifest builder.
"""
from __future__ import annotations

from typing import Any, Iterable


class ConfigFormError(ValueError):
    """Raised when a widget value can't be coerced to its target type."""


_SUPPORTED_METRICS = {
    "mean", "median", "std", "bg_median", "signal", "signal_median",
    "n_signal_px", "n_bg_px", "partial_disk",
}


def _to_int(value: str, label: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ConfigFormError(f"{label} must be an integer; got {value!r}")


def _to_float(value: str, label: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        raise ConfigFormError(f"{label} must be a number; got {value!r}")


def _opt_float(value: str, label: str) -> float | None:
    """Blank/whitespace → None; otherwise parse as float."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return _to_float(s, label)


def _opt_int(value: str, label: str) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return _to_int(s, label)


def _split_csv(value: str) -> list[str]:
    """Comma-separated string → list of stripped, non-empty tokens."""
    if not value:
        return []
    return [tok.strip() for tok in value.split(",") if tok.strip()]


def _rotation_deg(value: str) -> str | float:
    s = str(value).strip().lower()
    if s == "auto":
        return "auto"
    return _to_float(value, "lattice.rotation_deg")


def coerce_raw_values(raw: dict[str, Any]) -> dict[str, Any]:
    """Build a chipOid config dict from form widget values.

    `raw` is a flat dict keyed by widget name. Expected keys are documented
    inline below. Missing keys fall back to defaults from
    `chipoid.config.DEFAULTS` via deep-merge by the caller — this function
    only emits fields the form is responsible for.

    Returns a nested dict matching the schema of `chipoid.config.DEFAULTS`
    (so it can be deep-merged on top of the defaults).
    """
    # markers: comma-separated entry → list[str]
    markers = _split_csv(raw.get("markers", ""))
    if not markers:
        raise ConfigFormError("markers must be a non-empty comma-separated list")

    # readout.metrics: checkbox group → list[str]
    metric_flags = raw.get("metrics", {})
    if not isinstance(metric_flags, dict):
        raise ConfigFormError("metrics must be a dict of metric_name -> bool")
    metrics: list[str] = [m for m, on in metric_flags.items() if on]
    bad = set(metrics) - _SUPPORTED_METRICS
    if bad:
        raise ConfigFormError(f"unknown metrics enabled: {sorted(bad)}")

    extract_pages_raw = raw.get("extract_pages", {})
    if not isinstance(extract_pages_raw, dict):
        raise ConfigFormError("extract_pages must be a dict of channel -> int")
    extract_pages = {
        ch: _to_int(v, f"extract_channels.pages.{ch}")
        for ch, v in extract_pages_raw.items()
    }

    return {
        "input": {
            "manifest": raw.get("manifest", "configs/manifest.csv"),
            "data_root": raw.get("data_root", "data"),
            "extract_channels": {
                "enabled": bool(raw.get("extract_enabled", False)),
                "pages": extract_pages,
            },
        },
        "markers": markers,
        "detection": {
            "radius_min": _to_int(raw.get("radius_min", "35"), "radius_min"),
            "radius_max": _to_int(raw.get("radius_max", "50"), "radius_max"),
            "radius_step": _to_int(raw.get("radius_step", "1"), "radius_step"),
            "canny_sigma": _to_float(raw.get("canny_sigma", "2.0"), "canny_sigma"),
            "canny_low_threshold": _opt_float(raw.get("canny_low_threshold", ""), "canny_low_threshold"),
            "canny_high_threshold": _opt_float(raw.get("canny_high_threshold", ""), "canny_high_threshold"),
            "peak_threshold": _to_float(raw.get("peak_threshold", "0.30"), "peak_threshold"),
            "min_spacing": _to_int(raw.get("min_spacing", "110"), "min_spacing"),
            "max_peaks": _to_int(raw.get("max_peaks", "2000"), "max_peaks"),
        },
        "lattice": {
            "enabled": bool(raw.get("lattice_enabled", True)),
            "k_nn": _to_int(raw.get("k_nn", "4"), "k_nn"),
            "axis_band": _to_float(raw.get("axis_band", "50.0"), "axis_band"),
            "snap_tolerance": _to_float(raw.get("snap_tolerance", "30.0"), "snap_tolerance"),
            "rotation_deg": _rotation_deg(raw.get("rotation_deg", "auto")),
            "min_detected_fraction": _to_float(raw.get("min_detected_fraction", "0.25"), "min_detected_fraction"),
            "max_rows": _opt_int(raw.get("max_rows", ""), "max_rows"),
            "max_cols": _opt_int(raw.get("max_cols", ""), "max_cols"),
        },
        "readout": {
            "margin": _to_float(raw.get("margin", "4.0"), "margin"),
            "annulus_inner": _to_float(raw.get("annulus_inner", "8.0"), "annulus_inner"),
            "annulus_outer": _to_float(raw.get("annulus_outer", "20.0"), "annulus_outer"),
            "metrics": metrics,
        },
        "output": {
            "dir": raw.get("output_dir", "output"),
            "per_image_subdir": bool(raw.get("per_image_subdir", True)),
            "save_review_figure": bool(raw.get("save_review_figure", True)),
            "save_stage_overlays": bool(raw.get("save_stage_overlays", True)),
            "save_diagnostics": bool(raw.get("save_diagnostics", True)),
            "consolidated_csv": raw.get("consolidated_csv", "wells_all.csv"),
            "batch_summary_csv": raw.get("batch_summary_csv", "batch_summary.csv"),
            "keep_extracted": bool(raw.get("keep_extracted", True)),
        },
    }


def metric_descriptions() -> dict[str, str]:
    """Per-metric description text used in the GUI metric checkbox section."""
    return {
        "mean":          "Arithmetic mean of pixel values inside the signal disk (primary raw readout).",
        "median":        "Median of pixel values inside the signal disk; robust to bright outliers.",
        "std":           "Standard deviation inside the signal disk; heterogeneity proxy.",
        "bg_median":     "Median of pixel values inside the background annulus.",
        "signal":        "Background-subtracted: mean − bg_median. Primary readout for cross-image comparison.",
        "signal_median": "Robust alternative: median − bg_median.",
        "n_signal_px":   "Pixel count contributing to the signal disk (drops if disk is clipped at image edge).",
        "n_bg_px":       "Pixel count contributing to the background annulus.",
        "partial_disk":  "Boolean: true when the signal disk is truncated by the image edge.",
    }
