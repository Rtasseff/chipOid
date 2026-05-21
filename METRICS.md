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
| `x`, `y`        | float  | Pixel coordinates of well center (x = column-index, y = row-index). |
| `r`             | float  | Per-well radius from Hough (for `source=detected`) or `default_r` (for `source=filled`). The **readout** itself uses a single run-wide `r_well` (median of detected radii) — `r` here is reported for traceability. |
| `source`        | str    | `detected` if Hough found this well; `filled` if it was inferred from the lattice. |
| `dist_to_det`   | float  | Distance from the predicted grid point to the nearest Hough detection (px). 0 for filled wells with no nearby detection. |

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

`r_well` is the **median** of detected radii across the image (one scalar per
run, not per-well).

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
| `col_pitch`           | estimated column pitch (px) |
| `row_pitch`           | estimated row pitch (px) |
| `median_radius`       | `r_well` used for readout (px) |
| `signal_<m>_p5/median/p95` | per-image quantiles of per-well signal for each marker |

Use this to quickly QC a batch (which images had unusually low detection counts,
abnormally wide pitch, etc.) without opening per-image files.

## Cross-image normalization

For comparing wells across images or batches, **always subtract local background**
— use `signal_<m>` (or `signal_median_<m>`), not raw `mean_<m>`. The
annulus-based background absorbs per-image illumination and exposure variation.

For deeper normalization (e.g., adjusting for systematic intensity drift across
a plate run), use control wells: average their `signal_<m>` per image and divide.
That step is intentionally **not** built into chipOid — it's downstream analysis
that depends on the assay design.
