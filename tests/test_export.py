"""Workbook export + warn-and-continue behaviour (no seeded data needed)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from chipoid import __version__
from chipoid.config import load_config
from chipoid.export import safe_write, write_workbook


def _wells(inclusion: bool) -> pd.DataFrame:
    df = pd.DataFrame({
        "image_id": ["a", "a", "b", "b"],
        "well_id": ["r00c00", "r00c01", "r00c00", "r00c01"],
        "x": [10.5, 20.5, 10.5, 20.5],
        "source": ["detected", "filled", "detected", "detected"],
        "signal_green": [100.0, np.nan, 3.0, 400.0],
        "signal_red": [5.0, np.nan, 2.0, 1.0],
        "condition": ["c1", "c1", "c2", "c2"],
    })
    if inclusion:
        df.insert(4, "included", [True, False, False, True])
        df.insert(5, "exclude_reason", ["", "filled", "below_threshold", ""])
    return df


def _summary(inclusion: bool) -> pd.DataFrame:
    s = pd.DataFrame({"image_id": ["a", "b"], "n_wells": [2, 2]})
    if inclusion:
        s["n_included"] = [1, 1]
        s["min_signal_green"] = 50.0
        s["min_signal_red"] = 50.0
    return s


def _cfg(inclusion: bool) -> dict:
    cfg = load_config(None)
    cfg["inclusion"]["enabled"] = inclusion
    cfg["inclusion"]["min_signal"] = {"green": 50, "red": 60}
    return cfg


def _read(path, sheet):
    # keep_default_na so "" cells and real text behave predictably
    return pd.read_excel(path, sheet_name=sheet)


def _same(a: pd.DataFrame, b: pd.DataFrame) -> None:
    """dtype-insensitive, NaN-aware; empty string == missing."""
    a = a.replace("", np.nan).reset_index(drop=True)
    b = b.replace("", np.nan).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


@pytest.mark.parametrize("inclusion", [True, False])
def test_all_wells_matches_csv(tmp_path, inclusion):
    wells = _wells(inclusion)
    csv = tmp_path / "wells_all.csv"
    wells.to_csv(csv, index=False)
    xlsx = tmp_path / "wells_all.xlsx"
    assert write_workbook(xlsx, wells, _summary(inclusion), _cfg(inclusion), inclusion, print)
    _same(_read(xlsx, "all_wells"), pd.read_csv(csv))


def test_included_wells_sheet(tmp_path):
    wells = _wells(True)
    xlsx = tmp_path / "w.xlsx"
    write_workbook(xlsx, wells, _summary(True), _cfg(True), True, print)
    wb = load_workbook(xlsx)
    assert wb.sheetnames == ["all_wells", "included_wells", "summary", "settings"]
    inc = _read(xlsx, "included_wells")
    assert len(inc) == _read(xlsx, "summary")["n_included"].sum() == 2
    assert inc["included"].all()


def test_no_included_sheet_when_off(tmp_path):
    xlsx = tmp_path / "w.xlsx"
    write_workbook(xlsx, _wells(False), _summary(False), _cfg(False), False, print)
    assert load_workbook(xlsx).sheetnames == ["all_wells", "summary", "settings"]


def test_header_frozen_autofilter_values_only(tmp_path):
    xlsx = tmp_path / "w.xlsx"
    write_workbook(xlsx, _wells(True), _summary(True), _cfg(True), True, print)
    wb = load_workbook(xlsx)
    for name in ("all_wells", "included_wells"):
        ws = wb[name]
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref == ws.dimensions
    for ws in wb:
        assert not any(isinstance(c.value, str) and c.value.startswith("=")
                       for row in ws.iter_rows() for c in row)


def test_settings_sheet(tmp_path):
    xlsx = tmp_path / "w.xlsx"
    cfg = _cfg(True)
    write_workbook(xlsx, _wells(True), _summary(True), cfg, True, print)
    st = _read(xlsx, "settings")
    assert list(st.columns) == ["key", "value"]
    assert st["key"].iloc[0] == "chipoid_version"
    assert st["value"].iloc[0] == __version__
    assert st["key"].iloc[1] == "written_at"
    kv = dict(zip(st["key"], st["value"]))
    assert kv["inclusion.min_signal.green"] == 50
    assert kv["inclusion.min_signal.red"] == 60
    assert kv["markers"] == "green, red"
    assert kv["inclusion.enabled"] in (True, "TRUE")


def test_permission_error_warns_and_continues(tmp_path, monkeypatch):
    logs: list[str] = []

    def boom(*a, **k):
        raise PermissionError("[Errno 13] Permission denied: 'wells_all.xlsx'")

    monkeypatch.setattr(pd, "ExcelWriter", boom)
    ok = write_workbook(tmp_path / "wells_all.xlsx", _wells(False), _summary(False),
                        _cfg(False), False, logs.append)
    assert ok is False
    assert len(logs) == 1
    assert logs[0].startswith("  [WARN] could not write wells_all.xlsx (is it open in Excel?): ")


def test_safe_write_passes_other_errors_through(tmp_path):
    def bad():
        raise ValueError("not a lock problem")
    with pytest.raises(ValueError):
        safe_write(tmp_path / "x.csv", bad, print)
