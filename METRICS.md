# Output metrics reference

Per-well, per-marker metrics produced by chipOid. Pick which to emit via
`readout.metrics` in the config.

## Geometry (always emitted)

These describe **where** each well is, regardless of marker. One row per well in
`wells.csv` and `wells_all.csv`.

| Column          | Type   | Description |
|---|---|---|
| `image_id`      | str    | From the manifest. Identifies the source image. |
| `well_id`       | str    | `r{row:02d}c{col:02d}`, e.g. `r05c02`. Stable across reruns of the same image. |
| `row`, `col`    | int    | Lattice indices (0-based; smallest detected row/col = 0). |
| `x`, `y`        | float  | Pixel coordinates of well center (x = column-index, y = row-index). `detected` wells carry the exact Hough centre; `filled` wells sit at the fitted grid position. |
| `r`             | float  | Per-well radius from Hough (for `source=detected`) or `default_r` (for `source=filled`). The **readout** itself uses a single per-image `r_well` — the median radius of **all** Hough detections in the image (= `default_r`), not only of the wells that end up `detected` — so `r` here is reported for traceability. |
| `source`        | str    | `detected` if Hough found this well; `filled` if it was inferred from the lattice. |
| `dist_to_det`   | float  | Distance (px) from the fitted grid position to a Hough detection: for `detected` wells, the detection assigned to that grid point, i.e. the **lattice-fit residual**; for `filled` wells, the nearest Hough detection (never 0). `0` for every well when `lattice.enabled` is false. |

Plus any **metadata columns** carried from the manifest (`group`, `condition`,
`notes`, …) — propagated verbatim to every row of the image.

## Per-marker signal columns

For each marker `<m>` (e.g. `green`, `red`), the columns below are emitted **only
if listed in `readout.metrics`** in the config. Each is suffixed with the marker
name in the output CSV (e.g. `mean_green`, `signal_red`).

### Sampling geometry recap

For each well:
- **Signal disk**: filled disk of radius `r_well - margin`, centered on the well.
- **Guard ring**: pixels in `[r_well - margin, r_well + ann_inner]` are excluded from both signal and background — they may include the trap-chamber rim or sub-pixel edge artifacts.
- **Bg annulus**: ring `[r_well + ann_inner, r_well + ann_outer]` around the well, used as the local background reference.

`r_well` is the **median radius of all Hough detections** in the image
(`default_r` from the lattice stage; one scalar per image, not per-well), so
every well in an image is sampled with the same disk size.

### Available metrics

| Metric             | Type    | Definition                                                                              |
|---|---|---|
| `mean_<m>`         | float   | Arithmetic mean of pixel values inside the signal disk. **Primary "raw" readout.**       |
| `median_<m>`       | float   | Median of pixel values inside the signal disk. Robust to bright outliers (hot pixels, dust).|
| `std_<m>`          | float   | Standard deviation inside the signal disk. Heterogeneity proxy — high values may indicate partial coverage, focus drift, or mixed populations. |
| `bg_median_<m>`    | float   | Median of pixel values inside the bg annulus. Robust to dim halos from neighbors.        |
| `signal_<m>`       | float   | `mean_<m> − bg_median_<m>`. **Primary background-subtracted readout** — use this for cross-image comparison. Mean for signal (conventional fluorescence quantity); median for bg (robust to ring contamination). |
| `signal_median_<m>`| float   | `median_<m> − bg_median_<m>`. Fully-robust alternative readout. Use when bright outlier pixels (hot spots, single very bright cells) inflate `mean`. |
| `n_signal_px_<m>`  | int     | Pixel count in the signal disk. Should be constant across all wells *unless* a well is clipped by the image edge — then this drops. |
| `n_bg_px_<m>`      | int     | Pixel count in the bg annulus. Constant unless clipped at image edge. |
| `partial_disk_<m>` | bool    | `True` if the signal disk lost pixels to image-edge clipping. Filter these out for clean comparisons. |

## Inclusion columns (only when `inclusion.enabled`)

Two extra columns in `wells.csv`, `wells_all.csv` and the workbook, placed
**right after `dist_to_det`** (before the per-marker columns). When inclusion is
off they are absent and the CSV columns match v0.9.

| Column           | Type | Description |
|---|---|---|
| `included`       | bool | `True` if the well is kept, `False` if excluded. |
| `exclude_reason` | str  | `""` for included wells; otherwise `filled`, `partial_disk` or `below_threshold`. |

`exclude_reason`, first match wins in this precedence:
1. `filled` — `inclusion.exclude_filled` is on and `source` is `filled`.
2. `partial_disk` — `inclusion.exclude_partial` is on and any marker's signal disk lost pixels to image-edge clipping (same condition as `partial_disk_<m>`).
3. `below_threshold` — see the rule below.

**Rule:** keep a well if **any** marker's metric (`inclusion.metric`: `signal` or `signal_median`) is **≥** that marker's threshold. So `below_threshold` means *every* marker is below its threshold. A value exactly at the threshold is kept; NaN counts as below. The rule is not configurable.

Thresholds (`inclusion.min_signal`) are **raw counts after background subtraction**, the same units as `signal_<m>`, so they depend on exposure and gain and are not normalized across images. The rule reads the measurement itself, so `signal` need not be listed in `readout.metrics`. Excluded wells are flagged, not removed: filter on `included`.

## Raw Hough detections (`hough_centers.csv`)

Per-image diagnostic file listing every Hough detection BEFORE the lattice step
filters / supplements them. Use for debugging detection issues. Columns:

| Column  | Description |
|---|---|
| `x`, `y` | Pixel coordinates of detected circle center |
| `r`      | Detected radius (px) |
| `score`  | Normalized Hough vote at this peak, in `[0, 1]`. Comes from `skimage.transform.hough_circle_peaks` with `normalize=True`: each pixel's vote is divided by the candidate circle's perimeter, so larger circles aren't unfairly preferred. The detection-step config `detection.peak_threshold` (default 0.30) is the minimum score required for a peak to be returned — meaning "at least 30% of the global max vote count." Higher `score` = stronger geometric evidence for a circle at that position. |

## Batch summary (`batch_summary.csv`)

One row per image, with image-level counts and intensity quantiles:

| Column | Description |
|---|---|
| `image_id`            | from manifest |
| `n_hough`             | number of Hough detections before lattice |
| `n_wells`             | total well count after lattice (= n_detected + n_filled) |
| `n_detected`          | wells confirmed by Hough |
| `n_filled`            | wells filled in by lattice geometry only |
| `col_pitch`           | column pitch (px) of the refit lattice |
| `row_pitch`           | row pitch (px) of the refit lattice |
| `lattice_resid_median` | median lattice-fit residual (px) = median `dist_to_det` of `detected` wells after trimming. NaN when the lattice is disabled |
| `lattice_resid_p95`   | 95th percentile of the same residuals (px). NaN when the lattice is disabled |
| `median_radius`       | `r_well` used for readout (px) |
| `signal_<m>_p5/median/p95` | per-image quantiles of per-well signal for each marker |
| `n_included`          | wells with `included = True` (only when inclusion is on) |
| `min_signal_<m>`      | threshold applied to marker `<m>` (raw counts after background subtraction; one column per marker, only when inclusion is on) |

`col_pitch` / `row_pitch` are the geometry of the least-squares **refit** grid
(not the initial median-NN estimate). The residuals also appear in `run.log` as
`lattice QC: residual median=… p95=… px (refit iterations N, rescued M)`, with a
`[WARN]` when the median exceeds 0.25 × `r_well`.

Use this to quickly QC a batch (which images had unusually low detection counts,
abnormally wide pitch, a poor lattice fit, etc.) without opening per-image files.

## Excel workbook (`wells_all.xlsx`)

Written next to the consolidated CSV (same stem as `output.consolidated_csv`)
unless `output.xlsx` is false. **Values only, no formulas.** The header row is
frozen and the data sheets have an autofilter.

| Sheet            | Contents |
|---|---|
| `all_wells`      | Same rows and columns as `wells_all.csv`. |
| `included_wells` | Only when inclusion is on: the `all_wells` rows with `included = True`. |
| `summary`        | Same rows and columns as `batch_summary.csv`. |
| `settings`       | `key` / `value` rows: `chipoid_version`, `written_at`, then every effective config value under a dotted key (e.g. `inclusion.min_signal`; lists comma-joined). Includes the input and output paths. |

If the file is open in Excel when chipOid writes it, the write is skipped with a
`[WARN]` in `run.log` and the run continues; the CSVs are unaffected.

## Cross-image normalization

For comparing wells across images or batches, **always subtract local background**
— use `signal_<m>` (or `signal_median_<m>`), not raw `mean_<m>`. The
annulus-based background absorbs per-image illumination and exposure variation.

For deeper normalization (e.g., adjusting for systematic intensity drift across
a plate run), use control wells: average their `signal_<m>` per image and divide.
That step is intentionally **not** built into chipOid — it's downstream analysis
that depends on the assay design.
