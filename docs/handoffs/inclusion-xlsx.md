# Handoff — `feat/inclusion-xlsx`

| | |
|---|---|
| Branch | `feat/inclusion-xlsx` |
| Worktree dir | `~/projects/miniProjects/202605_chipOid-wt/inclusion-xlsx/` |
| Base | `main` @ `f993e5e` |
| Created | 2026-10-08 |
| Suggested model / effort | Sonnet 5.5 / high |
| Issues | Closes #1 · Closes #2 · Refs #7 (excluded-well marking only) |
| Coordinator session | `main` checkout at `~/projects/miniProjects/202605_chipOid/` |

Read this first, then `CLAUDE.md`, then GitHub issues #1, #2 and #7
(`gh issue view 1`, …). This directory is a git worktree: it *is* this branch.
Do not `git checkout` another branch here. Machine-specific paths (EXP24 data,
baseline outputs, validation commands) are in `LOCAL_SETUP.md` (gitignored,
copied in).

## Goal

The lab computes per-well %Live = green / (green + red) and averages over
wells. Empty wells have both signals in the noise, so their ratio sits around
50 % and drags every condition toward 50/50. On the EXP24 kill control,
chipOid v0.9 says 48.8 % live; the manual analysis says 3 %. Users currently
delete empty wells by hand in Excel. This branch adds:

1. an **inclusion step**: exclude a well only when **every** marker's signal is below its threshold;
2. an **Excel workbook** with an `all_wells` sheet and an `included_wells` sheet;
3. **excluded wells drawn in grey** on the overlays, with threshold lines on the scatter, so users can check the threshold by eye.

The threshold is a noise/occupancy QC, not a cell detector or a live/dead
classifier. Users judge "are there cells" from the brightfield; this is a
fluorescence proxy for that.

## Scope

**In:**
- the config block + validation
- new `src/chipoid/inclusion.py`, wired into `pipeline.py`
- new `src/chipoid/export.py` (the workbook)
- warn-and-continue around output writes
- the chipOid version on the first `run.log` line
- the #7 marking in `viz.py`
- `configs/default.yaml`
- tests

**Out** (do not do here):
- GUI widgets, `config_form_logic.py`, `chipoid_gui.spec`, `pyproject.toml` version handling. Branch `feat/gui-v010` does these, building against the contract below.
- Lattice changes (branch `fix/lattice-refit`).
- #7 beyond the marking: colour-scale floor, per-marker review histogram, title rewording.
- Per-well fraction columns (#8), SNR mode (#10).
- `README.md` / `METRICS.md`. Leave notes in "Notes for the docs pass".

## Contract (fixed; the GUI branch relies on it)

**Config** (`DEFAULTS` in `config.py` and `configs/default.yaml`, with comments):
```yaml
inclusion:
  enabled: false        # pipeline/CLI default = v0.9 behaviour (all wells included). The GUI turns it on.
  metric: signal        # signal | signal_median
  min_signal: 50        # a number = same threshold for every marker,
                        # or {marker: number} with an entry for EVERY marker
  exclude_filled: false # also exclude lattice-filled wells
  exclude_partial: true # also exclude wells whose signal disk is clipped by the image edge
output:
  xlsx: true            # write <stem of consolidated_csv>.xlsx next to it
```
- `_validate`, only when `inclusion.enabled`:
  - `metric` must be `signal` or `signal_median`.
  - `min_signal` is either a number ≥ 0 (not a bool), or a dict whose keys are exactly `markers`; name any missing or unknown keys in the error.
  - Each value is a number ≥ 0.
- The GUI always sends `min_signal` as a dict covering every marker; the CLI default is the scalar 50.

**Rule** (not configurable): keep a well if ANY marker's `metric` ≥ that marker's threshold. It's `≥`, so a value exactly at the threshold is kept. NaN counts as below.

**Exclusion reason**, first match wins:
1. `filled`: `exclude_filled` and `source == "filled"`.
2. `partial_disk`: `exclude_partial` and any marker's partial-disk flag is True.
3. `below_threshold`.

Included wells get `exclude_reason = ""`.

**Missing companion with inclusion on:** that image fails with
`ValueError("[<image_id>] inclusion is enabled but the '<marker>' companion is missing: <path>")`.
The existing per-image `try` logs it, and the batch continues with the other images.

**Use the measurement arrays, not the `wells` columns.** `signal_<m>` and
`partial_disk_<m>` only exist if they are listed in `readout.metrics`. Keep
the full `measure_marker` output per marker inside `process_image` and feed
that to the inclusion step.

**Per-well columns** (only when enabled): `included` (bool) and `exclude_reason` (str), inserted right after `dist_to_det`. **When disabled:** no new columns, and `wells.csv` / `wells_all.csv` are byte-identical to v0.9 for the same inputs.

**`batch_summary.csv`** (only when enabled): append `n_included`, then `min_signal_<m>` for each marker (the threshold used).

**`run.log`:**
- First line: `chipOid <__version__> batch: <n> images, config=..., data_root=..., out_root=...`. This is the only version change in this branch.
- After the effective-config dump, one of:
  - `inclusion: on — keep a well if ANY marker's signal ≥ its threshold: green ≥ 50, red ≥ 50 (exclude_filled=False, exclude_partial=True)`
  - `inclusion: off — all wells included`
- Per image, after the readout lines: `  inclusion: 19/100 wells included (81 below_threshold, 0 filled, 0 partial_disk)`.

**Workbook** (`output.xlsx: true`): `<out_root>/<stem of consolidated_csv>.xlsx`, i.e. `wells_all.xlsx`.
- Sheets:
  - `all_wells`: the same rows and columns as `wells_all.csv`.
  - `included_wells`: only when inclusion is enabled; rows with `included == True`.
  - `summary`: the `batch_summary.csv` rows.
  - `settings`: two columns, `key` and `value`. First `chipoid_version`, then `written_at` (ISO local time), then every effective-config leaf with a dotted key (e.g. `inclusion.min_signal.green`). Lists joined with ", ".
- Values only, no formulas.
- Freeze the header row and add an autofilter on the data sheets.
- Engine: openpyxl (already a dependency on `main`).

**Output writes: warn and continue.** Writing `wells_all.xlsx`, `wells_all.csv`, `batch_summary.csv` or a per-image `wells.csv` can raise `PermissionError` (usually because the file is open in Excel on Windows). When it does, log `  [WARN] could not write <name> (is it open in Excel?): <error>` and carry on. An open file must never fail an image or end the batch with a traceback.

**Module layout:**
- `src/chipoid/inclusion.py`: pure functions, no I/O. For example:
  - `resolve_thresholds(inc_cfg, markers) -> dict[str, float]`
  - `apply_inclusion(source, per_marker_metrics, thresholds, metric, exclude_filled, exclude_partial) -> (included: bool array, reason: object array)`
  - a small summary helper for the log line
- `src/chipoid/export.py`: `write_workbook(path, wells_all, summary, cfg, inclusion_enabled, log)`.

The GUI branch adds both module names to the PyInstaller spec, so keep these exact names.

**#7 marking (`viz.py`):**
- `save_intensity_overlay`, `save_scatter` and `save_review_figure` take an optional `included` argument (the scatter also takes `thresholds`). With `None`, output is unchanged.
- Intensity panels: excluded wells get a light grey fill (`#bdbdbd`, same alpha) with a dashed grey edge instead of a colormap colour. Keep the colour scale exactly as today.
- Scatter (07 and the review panel): included wells steelblue, excluded wells light grey. Dashed grey threshold lines at x = T(marker 1) and y = T(marker 2). Legend `included (n)` / `excluded (n)`.
- Review lattice-panel title: append ` · <n> included` when inclusion is on.

## Acceptance

**Tests:**
- [ ] `tests/test_inclusion.py`:
  - `resolve_thresholds`: scalar, dict, missing marker, unknown key, negative value, bool rejected.
  - `apply_inclusion`: both low → excluded `below_threshold`; green-only high → kept; red-only high → kept; NaN → excluded; exactly at threshold → kept.
  - `apply_inclusion` options: `exclude_filled`; `exclude_partial`; reason precedence `filled` > `partial_disk` > `below_threshold`; `signal_median` used when chosen.
  - Config `_validate` cases.
- [ ] `tests/test_export.py`:
  - `all_wells` read back with pandas equals the CSV (dtype-insensitive, NaN-aware).
  - `included_wells` row count = `n_included`, and the sheet is absent when inclusion is off.
  - `settings` has `chipoid_version`.
  - A forced `PermissionError` logs the warning, and the CSVs are still written.
- [ ] `tests/test_pipeline_in_memory.py` (skips without seeded data):
  - Inclusion off → no `included` column, and the xlsx has no `included_wells`.
  - Inclusion on → the columns are present and `n_included` is in the summary.
- [ ] Full suite green; record the count (baseline 41).

**EXP24.** Commands are in `LOCAL_SETUP.md`. Do two runs: `inclusion_off`, and `inclusion_on` (add `inclusion: {enabled: true}` to the copied config). Paste the `scripts/validate_exp.py` tables into the PR.
- [ ] **Off**: zero metric changes against `baseline_v0.9` on all 4 images and no extra columns. `cmp` shows `wells_all.csv` and every per-image `wells.csv` byte-identical to the baseline.
- [ ] **On**: the "included (run)" column equals the `T = 50` column on all 4 images (TX100: 20 / 2.5 / 2.1). TX100 vs picks: 99/100. The one extra is `r00c02`, a known misplaced filled well that `fix/lattice-refit` fixes.
- [ ] `wells_all.xlsx` opens with openpyxl and has the four sheets, and the `included_wells` row count equals the sum of `n_included`.
- [ ] TX100's `04_intensity_green.png`, `07_scatter.png` and `review.png`: excluded wells grey, threshold lines visible.

## Conflict watchlist

- `src/chipoid/pipeline.py`: `fix/lattice-refit` adds lattice QC log lines and two `summary` entries (`lattice_resid_median`, `lattice_resid_p95`, after `row_pitch`). It will probably merge first, so rebase before the PR. Expect only a small conflict in the summary dict.
- `config.py`, `viz.py`, `configs/default.yaml`: only this branch.

## Status

- [x] Config + validation
- [x] inclusion.py + wiring
- [x] export.py + write guards
- [x] viz marking
- [x] Tests
- [x] EXP24 acceptance tables
- Tests: 90 passed (baseline 41).
- Deviations: (1) `config._validate` calls `inclusion.resolve_thresholds` instead of duplicating the checks (inf is also rejected). (2) With inclusion on, the scatter (07 and review) plots the metric the thresholds apply to (`signal` or `signal_median`) so the lines sit on the plotted axes; `save_review_figure` got extra optional args `scatter_signals`, `thresholds`, `scatter_metric`; `save_scatter`'s `thresholds` is an `(x, y)` tuple. (3) With inclusion on, the missing-companion check runs right after input resolution (before detection), so no partial outputs. (4) Overlays are drawn after all markers are measured (needed so `included` is known); log lines and outputs are unchanged when off.
- [ ] PR open

## Notes for the docs pass

- Config: `inclusion.enabled` (default false), `.metric` (signal | signal_median), `.min_signal` (number, or {marker: number} covering every marker), `.exclude_filled` (false), `.exclude_partial` (true); `output.xlsx` (true).
- Rule: keep if ANY marker's metric >= its threshold (>=; NaN = below). Per-well columns `included`, `exclude_reason` (`filled` > `partial_disk` > `below_threshold`; "" if included), after `dist_to_det`, only when enabled.
- batch_summary (enabled): `n_included`, `min_signal_<marker>`. run.log: version on line 1, `inclusion: on/off` line after the config dump, per-image `inclusion: n/N wells included (...)` line.
- Workbook `<stem of consolidated_csv>.xlsx`: `all_wells`, `included_wells` (only if inclusion on), `summary`, `settings` (key/value; chipoid_version, written_at, every effective-config leaf). Values only; header frozen + autofilter.
- Users: thresholds are raw counts after bg subtraction, so they depend on exposure/gain; one setting per batch. A missing companion fails that image when inclusion is on. A write blocked by Excel (PermissionError) is a `[WARN]` and the run continues. `settings` contains absolute data_root / output.dir paths (account name on Windows).
- Pre-existing, not fixed: `save_histograms` (06) reads `wells["signal_<m>"]`, so any image fails with KeyError if `signal` is not in `readout.metrics`; a companion shape mismatch raises `SystemExit`, which the per-image `except Exception` does not catch, so it kills the batch.

## Questions for the coordinator

-

## Return protocol

1. Keep **Status** current; note any deviation from this brief.
2. `pytest tests/` passes; record the count against the baseline (41).
3. `git fetch origin && git rebase origin/main`, then re-run the tests. If `fix/lattice-refit` has merged by then, re-run the `inclusion_on` EXP24 check too; TX100 vs picks should now be 100/100.
4. Push the branch and open a PR against `main` with `Closes #1`, `Closes #2`, `Refs #7`. PR body = the review packet: what changed and why, deviations from the brief, test counts, the EXP24 tables, and any pre-existing bug you noticed but did not fix.
5. Tell the human the PR is up. The coordinator spot-checks and merges.
