"""Tests for chipoid.gui.config_form_logic.coerce_raw_values (no Tk needed)."""
from __future__ import annotations

import pytest

from chipoid.gui.config_form_logic import (
    ConfigFormError,
    coerce_raw_values,
    metric_descriptions,
)


def _default_raw() -> dict:
    """Form-state dict that mirrors the GUI defaults."""
    return {
        "markers": "green, red",
        "extract_enabled": False,
        "extract_pages": {"brightfield": 0},
        "radius_min": "35",
        "radius_max": "50",
        "radius_step": "1",
        "canny_sigma": "2.0",
        "canny_low_threshold": "",
        "canny_high_threshold": "",
        "peak_threshold": "0.30",
        "min_spacing": "110",
        "max_peaks": "2000",
        "lattice_enabled": True,
        "k_nn": "4",
        "axis_band": "50.0",
        "snap_tolerance": "30.0",
        "rotation_deg": "auto",
        "min_detected_fraction": "0.25",
        "max_rows": "",
        "max_cols": "",
        "margin": "4.0",
        "annulus_inner": "8.0",
        "annulus_outer": "20.0",
        "metrics": {m: True for m in metric_descriptions().keys()},
        "per_image_subdir": True,
        "save_review_figure": True,
        "save_stage_overlays": True,
        "save_diagnostics": True,
    }


def test_defaults_round_trip_to_expected_cfg_shape():
    cfg = coerce_raw_values(_default_raw())
    assert cfg["markers"] == ["green", "red"]
    assert cfg["detection"]["radius_min"] == 35
    assert cfg["detection"]["canny_low_threshold"] is None
    assert cfg["detection"]["canny_high_threshold"] is None
    assert cfg["lattice"]["rotation_deg"] == "auto"
    assert cfg["lattice"]["min_detected_fraction"] == 0.25
    assert cfg["lattice"]["max_rows"] is None
    assert cfg["lattice"]["max_cols"] is None
    assert set(cfg["readout"]["metrics"]) == set(metric_descriptions().keys())
    assert cfg["output"]["per_image_subdir"] is True
    assert cfg["input"]["extract_channels"]["enabled"] is False


def test_blank_canny_threshold_becomes_none():
    raw = _default_raw()
    raw["canny_low_threshold"] = "   "  # whitespace only
    cfg = coerce_raw_values(raw)
    assert cfg["detection"]["canny_low_threshold"] is None


def test_numeric_canny_threshold_is_parsed():
    raw = _default_raw()
    raw["canny_low_threshold"] = "12.5"
    cfg = coerce_raw_values(raw)
    assert cfg["detection"]["canny_low_threshold"] == 12.5


def test_rotation_auto_stays_string():
    raw = _default_raw()
    raw["rotation_deg"] = "AUTO"
    cfg = coerce_raw_values(raw)
    assert cfg["lattice"]["rotation_deg"] == "auto"


def test_rotation_numeric_becomes_float():
    raw = _default_raw()
    raw["rotation_deg"] = "-0.5"
    cfg = coerce_raw_values(raw)
    assert cfg["lattice"]["rotation_deg"] == -0.5


def test_rotation_invalid_raises():
    raw = _default_raw()
    raw["rotation_deg"] = "not-a-number"
    with pytest.raises(ConfigFormError, match="rotation_deg"):
        coerce_raw_values(raw)


def test_invalid_int_raises_with_label():
    raw = _default_raw()
    raw["radius_min"] = "thirty-five"
    with pytest.raises(ConfigFormError, match="radius_min"):
        coerce_raw_values(raw)


def test_markers_empty_raises():
    raw = _default_raw()
    raw["markers"] = ""
    with pytest.raises(ConfigFormError, match="markers"):
        coerce_raw_values(raw)


def test_metric_subset_emits_subset():
    raw = _default_raw()
    # keep only 'signal' and 'mean'
    raw["metrics"] = {m: (m in {"signal", "mean"}) for m in raw["metrics"]}
    cfg = coerce_raw_values(raw)
    assert set(cfg["readout"]["metrics"]) == {"signal", "mean"}


def test_unknown_metric_raises():
    raw = _default_raw()
    raw["metrics"] = {"signal": True, "totally_fake_metric": True}
    with pytest.raises(ConfigFormError, match="unknown metrics"):
        coerce_raw_values(raw)


def test_max_rows_blank_is_none_numeric_is_int():
    raw = _default_raw()
    raw["max_rows"] = "  "
    raw["max_cols"] = "4"
    cfg = coerce_raw_values(raw)
    assert cfg["lattice"]["max_rows"] is None
    assert cfg["lattice"]["max_cols"] == 4


def test_extract_pages_parsed_as_ints():
    raw = _default_raw()
    raw["extract_enabled"] = True
    raw["extract_pages"] = {"brightfield": "0", "green": "1", "red": "2"}
    raw["markers"] = "green, red"
    cfg = coerce_raw_values(raw)
    assert cfg["input"]["extract_channels"]["enabled"] is True
    assert cfg["input"]["extract_channels"]["pages"] == {
        "brightfield": 0, "green": 1, "red": 2,
    }
