"""Unit tests for the inclusion rule and its config validation (no I/O)."""
from __future__ import annotations

import numpy as np
import pytest

from chipoid.config import DEFAULTS, _validate, load_config
from chipoid.inclusion import (apply_inclusion, describe, format_image_line,
                               resolve_thresholds, summarize)

MARKERS = ["green", "red"]


def _m(signal, partial=None, signal_median=None):
    signal = np.asarray(signal, float)
    return {
        "signal": signal,
        "signal_median": signal if signal_median is None else np.asarray(signal_median, float),
        "partial_disk": np.zeros(len(signal), bool) if partial is None else np.asarray(partial, bool),
    }


def _apply(green, red, source=None, thresholds=None, metric="signal",
           exclude_filled=False, exclude_partial=False, partial=None,
           green_median=None, red_median=None):
    n = len(green)
    return apply_inclusion(
        np.array(source if source is not None else ["detected"] * n),
        {"green": _m(green, partial, green_median), "red": _m(red, partial, red_median)},
        thresholds or {"green": 50.0, "red": 50.0},
        metric, exclude_filled, exclude_partial,
    )


# ---- resolve_thresholds ---------------------------------------------------
def test_resolve_scalar():
    assert resolve_thresholds({"min_signal": 50}, MARKERS) == {"green": 50.0, "red": 50.0}


def test_resolve_dict():
    t = resolve_thresholds({"min_signal": {"green": 10, "red": 0}}, MARKERS)
    assert t == {"green": 10.0, "red": 0.0}


def test_resolve_missing_marker_named():
    with pytest.raises(ValueError, match=r"missing marker\(s\) \['red'\]"):
        resolve_thresholds({"min_signal": {"green": 10}}, MARKERS)


def test_resolve_unknown_key_named():
    with pytest.raises(ValueError, match=r"unknown key\(s\) \['blue'\]"):
        resolve_thresholds({"min_signal": {"green": 1, "red": 1, "blue": 1}}, MARKERS)


@pytest.mark.parametrize("bad", [-1, {"green": -5, "red": 1}, float("nan"), float("inf")])
def test_resolve_rejects_negative_nan_inf(bad):
    with pytest.raises(ValueError):
        resolve_thresholds({"min_signal": bad}, MARKERS)


@pytest.mark.parametrize("bad", [True, {"green": True, "red": 1}, "50", None])
def test_resolve_rejects_bool_and_non_numbers(bad):
    with pytest.raises(ValueError):
        resolve_thresholds({"min_signal": bad}, MARKERS)


# ---- apply_inclusion: the rule -------------------------------------------
def test_both_low_excluded_below_threshold():
    inc, reason = _apply([1], [2])
    assert not inc[0] and reason[0] == "below_threshold"


def test_green_only_high_kept():
    inc, reason = _apply([500], [2])
    assert inc[0] and reason[0] == ""


def test_red_only_high_kept():
    inc, reason = _apply([2], [500])
    assert inc[0] and reason[0] == ""


def test_nan_counts_as_below():
    inc, reason = _apply([np.nan], [np.nan])
    assert not inc[0] and reason[0] == "below_threshold"


def test_nan_in_one_marker_other_decides():
    inc, _ = _apply([np.nan], [500])
    assert inc[0]


def test_exactly_at_threshold_kept():
    inc, _ = _apply([50.0], [0.0])
    assert inc[0]
    inc, _ = _apply([49.999], [49.999])
    assert not inc[0]


def test_per_marker_thresholds():
    t = {"green": 10.0, "red": 1000.0}
    inc, _ = _apply([20, 5, 5], [0, 999, 1000], thresholds=t)
    assert list(inc) == [True, False, True]


# ---- apply_inclusion: options --------------------------------------------
def test_exclude_filled():
    src = ["detected", "filled"]
    inc, reason = _apply([500, 500], [500, 500], source=src, exclude_filled=True)
    assert list(inc) == [True, False] and reason[1] == "filled"
    inc, _ = _apply([500, 500], [500, 500], source=src, exclude_filled=False)
    assert list(inc) == [True, True]


def test_exclude_partial():
    inc, reason = _apply([500, 500], [500, 500], partial=[False, True], exclude_partial=True)
    assert list(inc) == [True, False] and reason[1] == "partial_disk"
    inc, _ = _apply([500, 500], [500, 500], partial=[False, True], exclude_partial=False)
    assert list(inc) == [True, True]


def test_reason_precedence():
    # well 0: filled+partial+low -> filled; well 1: partial+low -> partial_disk;
    # well 2: low only -> below_threshold; well 3: partial but high, option on -> partial_disk
    inc, reason = _apply(
        [0, 0, 0, 500], [0, 0, 0, 500],
        source=["filled", "detected", "detected", "detected"],
        partial=[True, True, False, True],
        exclude_filled=True, exclude_partial=True,
    )
    assert list(reason) == ["filled", "partial_disk", "below_threshold", "partial_disk"]
    assert not inc.any()


def test_partial_flag_from_any_marker():
    inc, reason = apply_inclusion(
        np.array(["detected"]),
        {"green": _m([500], [False]), "red": _m([500], [True])},
        {"green": 50.0, "red": 50.0}, "signal", False, True)
    assert not inc[0] and reason[0] == "partial_disk"


def test_signal_median_used_when_chosen():
    kw = dict(green_median=[0.0], red_median=[0.0])
    inc, _ = _apply([500], [500], metric="signal", **kw)
    assert inc[0]
    inc, reason = _apply([500], [500], metric="signal_median", **kw)
    assert not inc[0] and reason[0] == "below_threshold"


def test_summarize_and_log_line():
    inc, reason = _apply([500, 0, 0], [0, 0, 0], source=["detected", "filled", "detected"],
                         exclude_filled=True)
    c = summarize(inc, reason)
    assert c == {"n_wells": 3, "n_included": 1, "below_threshold": 1,
                 "filled": 1, "partial_disk": 0}
    assert format_image_line(c) == ("inclusion: 1/3 wells included "
                                    "(1 below_threshold, 1 filled, 0 partial_disk)")


def test_describe_strings():
    assert describe({"enabled": False}, MARKERS) == "inclusion: off — all wells included"
    inc = {"enabled": True, "metric": "signal", "min_signal": 50,
           "exclude_filled": False, "exclude_partial": True}
    assert describe(inc, MARKERS) == (
        "inclusion: on — keep a well if ANY marker's signal ≥ its threshold: "
        "green ≥ 50, red ≥ 50 (exclude_filled=False, exclude_partial=True)")


# ---- config validation ----------------------------------------------------
def _cfg(**inc):
    cfg = load_config(None)
    cfg["inclusion"].update(enabled=True, **inc)
    return cfg


def test_defaults_are_off_and_scalar():
    assert DEFAULTS["inclusion"]["enabled"] is False
    assert DEFAULTS["inclusion"]["min_signal"] == 50
    assert DEFAULTS["output"]["xlsx"] is True


def test_validate_ok_scalar_and_dict():
    _validate(_cfg())
    _validate(_cfg(min_signal={"green": 1, "red": 2}, metric="signal_median"))


def test_validate_bad_metric():
    with pytest.raises(ValueError, match="metric"):
        _validate(_cfg(metric="mean"))


def test_validate_dict_must_cover_markers():
    with pytest.raises(ValueError, match=r"missing marker\(s\) \['red'\]"):
        _validate(_cfg(min_signal={"green": 1}))
    with pytest.raises(ValueError, match=r"unknown key\(s\) \['blue'\]"):
        _validate(_cfg(min_signal={"green": 1, "red": 1, "blue": 1}))


@pytest.mark.parametrize("bad", [-1, True, {"green": -1, "red": 1}, "x"])
def test_validate_bad_values(bad):
    with pytest.raises(ValueError):
        _validate(_cfg(min_signal=bad))


def test_validate_skipped_when_disabled():
    cfg = load_config(None)
    cfg["inclusion"].update(enabled=False, metric="bogus", min_signal=-3)
    _validate(cfg)


def test_user_dict_replaces_scalar_default_in_merge(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("inclusion:\n  enabled: true\n  min_signal: {green: 5, red: 7}\n")
    assert load_config(p)["inclusion"]["min_signal"] == {"green": 5, "red": 7}
