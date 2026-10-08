"""Inclusion step: decide which wells hold a usable fluorescence signal.

Pure functions, no I/O. The rule is deliberately NOT configurable:

    keep a well if ANY marker's `metric` >= that marker's threshold.

A dead-control well has green in the noise and strong red; a fully live well
has red in the noise. Excluding on "either channel low" would discard exactly
the wells that matter, so a well is excluded only when EVERY marker is below
its threshold. `>=` means a value exactly at the threshold is kept; NaN counts
as below.

This is a noise/occupancy QC, not a cell detector or a live/dead classifier.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

REASON_FILLED = "filled"
REASON_PARTIAL = "partial_disk"
REASON_BELOW = "below_threshold"
REASONS = (REASON_BELOW, REASON_FILLED, REASON_PARTIAL)


def resolve_thresholds(inc_cfg: Mapping, markers: list[str]) -> dict[str, float]:
    """Turn `inclusion.min_signal` (scalar or per-marker dict) into {marker: T}.

    Raises ValueError for a dict whose keys are not exactly `markers`, or for
    any value that is not a number >= 0 (bools are rejected).
    """
    ms = inc_cfg["min_signal"]
    if isinstance(ms, Mapping):
        missing = [m for m in markers if m not in ms]
        unknown = [k for k in ms if k not in markers]
        if missing or unknown:
            parts = []
            if missing:
                parts.append(f"missing marker(s) {missing}")
            if unknown:
                parts.append(f"unknown key(s) {unknown}")
            raise ValueError(
                f"inclusion.min_signal must have exactly one entry per marker "
                f"{list(markers)}: " + "; ".join(parts)
            )
        raw = {m: ms[m] for m in markers}
    else:
        raw = {m: ms for m in markers}

    out: dict[str, float] = {}
    for m, v in raw.items():
        if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
            raise ValueError(f"inclusion.min_signal for '{m}' must be a number, got {v!r}")
        if not (v >= 0) or not np.isfinite(v):  # also rejects NaN
            raise ValueError(
                f"inclusion.min_signal for '{m}' must be a finite number >= 0, got {v!r}"
            )
        out[m] = float(v)
    return out


def apply_inclusion(source, per_marker_metrics: Mapping[str, Mapping[str, np.ndarray]],
                    thresholds: Mapping[str, float], metric: str,
                    exclude_filled: bool, exclude_partial: bool
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Return (included: bool array, reason: object array) in well order.

    Args:
      source:             per-well "detected"/"filled" labels (wells["source"]).
      per_marker_metrics: {marker: measure_marker() output}. Must contain
                          `metric` and "partial_disk" for every thresholded marker.
      thresholds:         {marker: T}; its keys define which markers count.
      metric:             "signal" or "signal_median".

    Reason, first match wins: `filled` > `partial_disk` > `below_threshold`.
    Included wells get reason "".
    """
    source = np.asarray(source)
    n = len(source)
    keep_any = np.zeros(n, dtype=bool)
    partial_any = np.zeros(n, dtype=bool)
    for marker, thr in thresholds.items():
        m = per_marker_metrics[marker]
        vals = np.asarray(m[metric], dtype=float)
        with np.errstate(invalid="ignore"):  # NaN >= T is False (and warns on old numpy)
            keep_any |= vals >= thr
        partial_any |= np.asarray(m["partial_disk"], dtype=bool)

    is_filled = (source == "filled") if exclude_filled else np.zeros(n, dtype=bool)
    is_partial = partial_any if exclude_partial else np.zeros(n, dtype=bool)

    reason = np.full(n, "", dtype=object)
    below = ~keep_any
    # Assign in reverse precedence so earlier rules overwrite later ones.
    reason[below] = REASON_BELOW
    reason[is_partial] = REASON_PARTIAL
    reason[is_filled] = REASON_FILLED
    included = reason == ""
    return included, reason


def summarize(included: np.ndarray, reason: np.ndarray) -> dict[str, int]:
    """Counts for the log/summary: n_wells, n_included and one count per reason."""
    out = {"n_wells": int(len(included)), "n_included": int(np.sum(included))}
    for r in REASONS:
        out[r] = int(np.sum(reason == r))
    return out


def format_image_line(counts: Mapping[str, int]) -> str:
    return (f"inclusion: {counts['n_included']}/{counts['n_wells']} wells included "
            f"({counts[REASON_BELOW]} {REASON_BELOW}, {counts[REASON_FILLED]} {REASON_FILLED}, "
            f"{counts[REASON_PARTIAL]} {REASON_PARTIAL})")


def describe(inc_cfg: Mapping | None, markers: list[str]) -> str:
    """The one-line batch description written to run.log after the config dump."""
    if not inc_cfg or not inc_cfg.get("enabled"):
        return "inclusion: off — all wells included"
    metric = inc_cfg["metric"]
    thr = resolve_thresholds(inc_cfg, markers)
    parts = ", ".join(f"{m} ≥ {t:g}" for m, t in thr.items())
    return (f"inclusion: on — keep a well if ANY marker's {metric} ≥ its threshold: "
            f"{parts} (exclude_filled={bool(inc_cfg['exclude_filled'])}, "
            f"exclude_partial={bool(inc_cfg['exclude_partial'])})")
