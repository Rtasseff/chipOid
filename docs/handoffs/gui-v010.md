# Handoff — `feat/gui-v010`

| | |
|---|---|
| Branch | `feat/gui-v010` |
| Worktree dir | `~/projects/miniProjects/202605_chipOid-wt/gui-v010/` |
| Base | `main` @ `f993e5e` |
| Created | 2026-10-08 |
| Suggested model / effort | Sonnet 5.5 / medium |
| Issues | Refs #5 (the `.exe` build and smoke test happen later, in the Windows session) |
| Coordinator session | `main` checkout at `~/projects/miniProjects/202605_chipOid/` |

Read this first, then `CLAUDE.md`, then GitHub issue #5 (`gh issue view 5`)
and the contract section of #1 / #2. This directory is a git worktree: it *is*
this branch. Do not `git checkout` another branch here.

## Goal

The lab uses only the packaged GUI (`chipOid.exe`), so nothing in v0.10 reaches
them until the GUI exposes it. This branch:
- adds GUI controls for the new empty-well exclusion and the Excel workbook;
- shows the chipOid version in the window title;
- single-sources the version number;
- gets the PyInstaller spec ready for the new modules.

The pipeline side is being built in parallel on `feat/inclusion-xlsx`. Build
against the contract below and don't wait for it.

## Scope

**In:**
- `src/chipoid/gui/config_form.py`
- `src/chipoid/gui/config_form_logic.py`
- `src/chipoid/gui/app.py`
- `chipoid_gui.spec`
- `pyproject.toml` (dynamic version)
- `tests/test_config_form_logic.py`

**Out** (do not do here):
- Pipeline, config defaults/validation, `inclusion.py`, `export.py`, viz (branch `feat/inclusion-xlsx`).
- The `run.log` version line (also `feat/inclusion-xlsx`).
- Bumping the version number (the coordinator does it at release).
- Building the `.exe` (Windows session).
- `README.md` / `METRICS.md` / `docs/WINDOWS_DESKTOP_BUNDLE.md` (coordinator's docs pass).

## Contract (fixed; must match `feat/inclusion-xlsx`)

The form's config overrides must include:
```python
"inclusion": {
    "enabled": bool,
    "metric": "signal",                          # not exposed in the GUI
    "min_signal": {marker: float, ...},          # ALWAYS a dict with one entry per current marker
    "exclude_filled": bool,
    "exclude_partial": bool,
},
"output": {..., "xlsx": bool},
```

**GUI defaults:**

| Option | Default |
|---|---|
| Exclusion | **on** |
| "Same threshold for all markers" | **on**, value `50` |
| Exclude filled | off |
| Exclude partial | **on** |
| Write xlsx | **on** |

The pipeline/CLI default stays off; only the GUI turns exclusion on.

**Validation in `coerce_raw_values`** (raise `ConfigFormError`, Tk-free):
- **Exclusion on:** every threshold parses as a float ≥ 0, and every current marker has one. The message names the field.
- **Exclusion off:** thresholds are not validated. Still emit the dict, using parsed values where valid and 50.0 otherwise, so turning it back on is painless.

## Widgets (`config_form.py`)

Use the existing widget classes in `widgets.py` (`CheckboxOption` with
`on_change`, `LabeledEntry`, `NoteLabel`) and the `_row(...)` helper, and
match the style of the other sections.

New `LabelFrame` **"Well inclusion (exclude empty wells)"**, after "Readout"
and before "Output figures":

- **"Exclude empty wells"** checkbox (`inclusion_enabled`). Note: "A well is excluded only when EVERY marker's background-subtracted signal is below its threshold (in the noise on all channels). Excluded wells stay in wells_all.csv and the all_wells sheet, flagged by the included / exclude_reason columns; the included_wells sheet leaves them out."
- **"Same threshold for all markers"** checkbox (`min_signal_same`), plus a "threshold (signal counts)" entry (`min_signal_all`, default `50`). Note: "Raw intensity after background subtraction, so it depends on exposure and gain. Pick it from the kill control or visibly empty wells and keep it fixed for an experiment. 50 worked on the validation data."
- **Per-marker threshold entries**, one `"threshold for '<marker>'"` entry per marker, shown only when "same for all" is off:
  - Rebuild them when the marker list changes, the same way `_rebuild_extract_pages` handles the extract-page spinboxes. Preserve existing values; new markers start at the shared value.
  - When the user switches "same for all" off, seed the per-marker fields with the shared value.
- **"Also exclude lattice-filled wells"** checkbox (`exclude_filled`, default off). Note: "Filled wells are placed from the grid, not seen by the detector."
- **"Also exclude wells clipped by the image edge"** checkbox (`exclude_partial`, default on).
- Optional nicety: grey out the sub-widgets while the main checkbox is off. Skip it if the widget classes make it awkward.

In **"Output figures"**:
- Add a checkbox **"Write Excel workbook (wells_all.xlsx)"** (`xlsx`, default on). Note: "Sheets: all_wells, included_wells (when exclusion is on), summary, settings."
- Consider renaming the section to "Output", since it's no longer only figures.

Extend `raw_values()` with `inclusion_enabled`, `min_signal_same`,
`min_signal_all`, `min_signal` (dict marker → str), `exclude_filled`,
`exclude_partial` and `xlsx`. Extend `coerce_raw_values` to emit the contract
above.

## Version

- `pyproject.toml`: replace the static `version` with `dynamic = ["version"]`, and add `[tool.setuptools.dynamic] version = {attr = "chipoid.__version__"}`. Re-run `pip install -e ".[dev]"` and check that `pip show chipoid` reports the version from `src/chipoid/__init__.py`.
- `app.py`:
  - Set `APP_TITLE = f"chipOid v{chipoid.__version__}"`.
  - Remove the hard-coded "v0.9" wherever it appears in GUI strings and docstrings.
  - If there's a developer-status subtitle, keep it, without a version number.

## Spec (`chipoid_gui.spec`)

- `hiddenimports`: add `'chipoid.inclusion'`, `'chipoid.export'` and `'openpyxl'`. The two chipoid modules come from the other branch; until it merges, a missing hidden import is only a warning.
- Add `collect_all('openpyxl')` alongside the other `collect_all` calls, and include its datas, binaries and hiddenimports.
- Don't try to build the Windows `.exe` from WSL; you can't. The Windows session does it after merge.

## Acceptance

- [ ] `tests/test_config_form_logic.py` (Tk-free):
  - The defaults emit `enabled: True`, `min_signal: {green: 50.0, red: 50.0}`, `exclude_filled: False`, `exclude_partial: True` and `xlsx: True`.
  - "Same for all" fills every marker.
  - Per-marker values pass through.
  - Renamed markers (e.g. `calcein, pi`) get matching keys.
  - Blank, negative or non-numeric thresholds raise `ConfigFormError` when exclusion is on, and don't when it's off.
- [ ] Full suite green; record the count (baseline 41).
- [ ] The merged config still loads:
  - `_deep_merge(DEFAULTS, form.to_cfg_overrides())`-style merging works.
  - A pipeline run from the GUI config on this branch doesn't crash. The pipeline ignores the `inclusion` block until the other branch merges.
- [ ] If WSLg gives you a display, launch `.venv/bin/chipoid-gui` and check:
  - the new section renders;
  - the per-marker fields rebuild when you edit markers;
  - "same for all" toggles them;
  - the title shows the version.

  If there's no display, say so in Status; the Windows smoke test covers it.

## Conflict watchlist

- `pyproject.toml`: once your dynamic-version change lands, the coordinator bumps `__version__` in `src/chipoid/__init__.py` at release, not `pyproject.toml`.
- `chipoid_gui.spec`, `src/chipoid/gui/*`: only this branch.

## Status

- [ ] Logic + tests
- [ ] Widgets
- [ ] Version
- [ ] Spec
- [ ] PR open

## Notes for the docs pass

<!-- Fill in:
     - the GUI section's fields and defaults (for README and the user guide);
     - the smoke-test checks the Windows session should add for the new
       section. -->

## Questions for the coordinator

-

## Return protocol

1. Keep **Status** current; note any deviation from this brief.
2. `pytest tests/` passes; record the count against the baseline (41).
3. `git fetch origin && git rebase origin/main`, then re-run the tests.
4. Push the branch and open a PR against `main` with `Refs #5`. PR body = the review packet: what changed and why, deviations from the brief, test counts, and any pre-existing bug you noticed but did not fix.
5. Tell the human the PR is up. The coordinator spot-checks and merges (after the other two).
