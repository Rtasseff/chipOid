"""Excel workbook export plus the warn-and-continue write helper.

Workbook layout (values only, no formulas):
  all_wells       same rows/columns as the consolidated CSV
  included_wells  only when inclusion is on; rows with included == True
  summary         the batch_summary rows
  settings        key/value: chipoid_version, written_at, then every
                  effective-config leaf under a dotted key

Writing can raise PermissionError (typically the file is open in Excel on
Windows). `safe_write` turns that into a log warning so an open file never
fails an image or ends the batch with a traceback.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from . import __version__


def safe_write(path: Path, write: Callable[[], None], log: Callable[[str], None]) -> bool:
    """Run `write()`; on PermissionError log a warning and return False."""
    try:
        write()
        return True
    except PermissionError as e:
        log(f"  [WARN] could not write {Path(path).name} (is it open in Excel?): {e}")
        return False


def _flatten(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Config leaves as (dotted_key, value). Lists are joined with ", "."""
    if isinstance(obj, dict) and obj:
        out: list[tuple[str, Any]] = []
        for k, v in obj.items():
            out.extend(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(obj, dict):
        return [(prefix, "")]
    if isinstance(obj, (list, tuple)):
        return [(prefix, ", ".join(str(x) for x in obj))]
    return [(prefix, "" if obj is None else obj)]


def settings_frame(cfg: dict) -> pd.DataFrame:
    rows: list[tuple[str, Any]] = [
        ("chipoid_version", __version__),
        ("written_at", datetime.now().isoformat(timespec="seconds")),
    ]
    rows.extend(_flatten(cfg))
    return pd.DataFrame(rows, columns=["key", "value"])


def _finish_sheet(ws, autofilter: bool) -> None:
    ws.freeze_panes = "A2"
    if autofilter and ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions
    # Readable column widths without opening the file blind.
    for col in ws.columns:
        longest = max((len(str(c.value)) for c in col if c.value is not None), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, longest + 2), 60)


def write_workbook(path: Path, wells_all: pd.DataFrame, summary: pd.DataFrame,
                   cfg: dict, inclusion_enabled: bool,
                   log: Callable[[str], None]) -> bool:
    """Write the workbook; returns False (after logging a warning) if the
    target could not be written because of a PermissionError."""
    path = Path(path)

    def _write() -> None:
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            wells_all.to_excel(xw, sheet_name="all_wells", index=False)
            data_sheets = ["all_wells"]
            if inclusion_enabled:
                inc = wells_all[wells_all["included"].astype(bool)]
                inc.to_excel(xw, sheet_name="included_wells", index=False)
                data_sheets.append("included_wells")
            summary.to_excel(xw, sheet_name="summary", index=False)
            data_sheets.append("summary")
            settings_frame(cfg).to_excel(xw, sheet_name="settings", index=False)
            for name, ws in xw.sheets.items():
                _finish_sheet(ws, autofilter=name in data_sheets)

    ok = safe_write(path, _write, log)
    if ok:
        log(f"workbook:          {path}")
    return ok
