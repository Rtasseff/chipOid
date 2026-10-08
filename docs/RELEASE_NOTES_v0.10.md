# chipOid v0.10.0 — release notes

> **DRAFT** until the v0.10 branches are merged and validated.

What changed since v0.9, in response to the September 2026 comparison against
manual Fiji analysis.

## New

- **Empty wells are excluded** (GUI: "Well inclusion", on by default, threshold 50).
  - A well is excluded only when green **and** red are both below the threshold, i.e. in the noise on every channel. Dead wells (red only) and live wells (green only) are kept.
  - Excluded wells stay in the output, marked with `included` and `exclude_reason` columns.
  - On EXP24 this takes the kill control from 48.8 % to ⟨x⟩ % live (manual Fiji: 3 %) and selects the same ⟨19⟩ wells you picked by hand.
- **Excel workbook** `wells_all.xlsx`, with sheets `all_wells`, `included_wells`, `summary` and `settings`. Values only, no formulas.
- **Figures show excluded wells in grey.** The scatter plot shows the threshold lines.
- **The window title and `run.log` show the chipOid version.**

## Fixed

- **Wells placed off-centre.** On some chips (EXP24 TX100), wells the detector had found were marked "filled" (magenta) and measured ~30 px above the real well. The grid fit is now refined against the detected wells, so they're measured in the right place. `run.log` reports the fit quality and warns if it's poor.
- **Excel holding a file open no longer breaks a run.** If a previous `wells_all.csv` or `.xlsx` is open in Excel, chipOid warns and carries on instead of failing.
- **Same numbers on Windows and Linux.** Detected wells now keep their exact detected centre.

## Compatibility

- **Exclusion on (GUI default):** you get two extra columns, `included` and `exclude_reason`. Everything else is the same as v0.9.
- **Exclusion off:** the CSV columns are identical to v0.9.
- **Changed wells:** wells that were previously misplaced (magenta wells near an actual trap) now have different, correct values.

## Not in this release

- Matching chipOid wells to Fiji ROIs one by one.
- Fixed colour scales across conditions.
- A per-well %Live column.
- Brightfield-based cell detection.

These are tracked as GitHub issues for later versions.
