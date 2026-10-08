# CLAUDE.md

## Project

**chipOid** — classical-CV well detection + fluorescence readout for microfluidic chip overviews. No deep learning. See `SegOid-chipOid_handoff.md` for the assessment that motivated splitting this off from SegOid.

The deliverable is per-well intensity statistics in a CSV (plus an Excel workbook): chipOid does not classify wells or normalize across images, and its optional inclusion step is only a noise/occupancy QC (a well is excluded only when EVERY marker's signal is below its threshold), not a cell detector or live/dead classifier.

## Tech stack

- Python 3.12, `.venv` at project root
- Package: `src/chipoid/` with submodules (config, manifest, extract, detect, lattice, readout, inclusion, export, viz, pipeline, cli)
- Installed in editable mode: `pip install -e .`
- CLI entry point: `chipoid` (subcommands: `run`, `extract`)
- GUI entry point: `chipoid-gui` or `python -m chipoid.gui` (Tkinter)
- Tests: `pytest tests/` (113 tests at v0.10, all green)
- Dependencies: numpy, scipy, scikit-image, tifffile, pandas, matplotlib, pyyaml, openpyxl

## Storage (this machine)

Code on SSD (tracked in git). `data/` and `output/` are symlinks to `/mnt/d/projects/chipOid/` (D drive, not backed up). See `LOCAL_SETUP.md`.

## Worktrees, handoffs and the Windows session

The v0.10 plan lives in GitHub issues (Rtasseff/chipOid, milestone `v0.10`). Large chunks of work run on their own branch in a sibling worktree under `~/projects/miniProjects/202605_chipOid-wt/<slug>/`, each with a fresh session. **If this checkout is a worktree, read `docs/handoffs/<slug>.md` first**: it is the branch's brief. Conventions: `docs/handoffs/README.md`. Validation against real data: `scripts/validate_exp.py` (paths in `LOCAL_SETUP.md`). Windows-only steps (building the `.exe`) run in a Windows session on this folder that reports back and never commits.

## BF + companion convention

Every input image is a small group of files all sharing one `<base>` stem and the same shape:

- `<base>.tif` — **brightfield ("BF")**, used only for geometry (finding wells).
- `<base>_<marker>.tif` — **companion**, one per fluorescence channel, used only for intensity readout.

Marker names are user-configurable in the config (`markers: [green, red]` by default; rename freely). The naming rule itself is fixed. Companions must match BF shape exactly. BF should be 8-bit (extraction step converts higher-bit-depth BF automatically); companions stay at their native dtype (typically uint16) so absolute intensities are preserved for measurement.

## Coordinate / type conventions inside the code

- `x` = column index, `y` = row index. `skimage.draw.disk` takes `(row, col)` = `(y, x)`.
- `wells` DataFrame is the canonical per-well object: columns `well_id, row, col, x, y, r, source, dist_to_det` (then `included, exclude_reason` when inclusion is on), plus per-marker metric columns (`mean_green`, `signal_red`, …), plus any manifest-metadata columns (`group`, `condition`, …) when written to CSV.

## Key files

| File | Purpose |
|---|---|
| `configs/default.yaml` | Full config schema with inline comments |
| `configs/manifest_example.csv` | Manifest template |
| `METRICS.md` | Per-column definitions for all output CSVs |
| `README.md` | User-facing docs (install, run, config, outputs, conventions) |
| `src/chipoid/pipeline.py` | Batch orchestrator (the canonical "what runs in what order") |
| `src/chipoid/inclusion.py` | Optional inclusion step (pure functions, no I/O): threshold resolution, the keep-if-ANY-marker-≥-threshold rule, `exclude_reason` precedence (filled > partial_disk > below_threshold). Config is validated through `resolve_thresholds` so config and runtime cannot disagree. |
| `src/chipoid/export.py` | `wells_all.xlsx` writer (`all_wells`, `included_wells`, `summary`, `settings`; values only) and `safe_write`, which turns a `PermissionError` (file open in Excel) into a `[WARN]` instead of failing the run. |
| `src/chipoid/readout.py` | Correctness-critical — sampling geometry, sanity checks. Heavily commented inline; review carefully on changes since outputs are hard to spot-check. |
| `src/chipoid/gui/` | Tkinter desktop app. `app.py` is the main window; `config_form.py` builds widgets; `config_form_logic.py` has the pure validation logic (tested without Tk). `manifest_builder.py` + `filename_schema.py` turn a folder of TIFFs into an in-memory manifest. `jobs.py` runs the pipeline on a worker thread; `logging_handler.py` routes log lines back to the main thread via a queue. |
| `chipoid_gui.spec` + `docs/WINDOWS_DESKTOP_BUNDLE.md` | PyInstaller spec and build instructions for the Windows `.exe`. |
| `scripts/validate_exp.py` | Validation against real data: compares a run's `wells_all.csv` with a baseline run and/or hand-picked wells and prints markdown tables. All paths are arguments; no data in the repo (paths in `LOCAL_SETUP.md`). |
| `docs/handoffs/` + `docs/WINDOWS_SESSION.md` | Per-branch briefs (conventions in `docs/handoffs/README.md`; each brief's "Notes for the docs pass" feeds README/METRICS) and the Windows-session protocol (build and smoke-test the `.exe`; reports back, never commits). |
| `tests/` | Unit tests for the lattice, inclusion, export and pure (non-Tk) GUI logic + an integration test for `pipeline.run_batch_in_memory`. Run with `pytest tests/`. |

## Running

```bash
chipoid run --config configs/default.yaml
```

Adjust `markers`, `detection.radius_min/max`, and `readout.metrics` for new datasets.

## Design notes

- **r_well is one value per image** (= median radius of all Hough detections, `default_r`). Every well in the image gets sampled with the same disk size so per-well means are directly comparable. Per-well detected `r` is still retained as a column for traceability.
- **Signal = mean − bg_median**: asymmetric stat is intentional (mean for signal = conventional fluorescence quantification; median for bg = robust to neighbor halos / hot pixels). `signal_median = median − bg_median` is also emitted as a robust alternative.
- **Lattice as a fallback, not a source**: well coordinates come from real Hough detections when available. The lattice fills gaps only when Hough misses a well. In practice on clean images Hough finds 100% and the lattice is just a sanity check.
- **Lattice refit**: the median-NN pitch only seeds the grid; a least-squares affine fit on the snapped detections sets the final grid positions; detected wells keep their exact Hough centre (platform-independent results).
- **Single chip per image**: a direct consequence of fitting one global lattice. Multi-chip images must be split upstream. Documented in README under "Why a lattice".
- **BF 8-bit conversion (in extraction step)**: required because Canny's default thresholds (10/20% of dtype max) only land in the right place when the BF is 8-bit. Higher-bit-depth BF works too but requires manually setting Canny thresholds in the config.

## What chipOid is deliberately NOT

- Not a classifier. No live/dead labels, no automatic thresholding of biology. Just per-well metrics in a CSV. The optional `inclusion` threshold is an occupancy/noise QC (exclude a well only when every marker is below it; excluded wells are flagged, never deleted), not classification. Classification belongs in downstream analysis where you have control wells and can set meaningful thresholds.
- Not a cross-image normalizer. Each image is processed independently. Absolute intensities across images depend on exposure/illumination and should be normalized downstream using your controls.
- Not a multi-chip handler (yet). One lattice = one chip per image.

## No PII in the repo

Dataset / sample names are scrubbed. `LOCAL_SETUP.md` is gitignored and contains machine-specific paths only.
