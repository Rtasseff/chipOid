# chipOid

Classical-CV well detector + fluorescence readout for microfluidic chip overview images.

The problem here is geometric (find wells on a lattice, read fluorescence), not biological — so chipOid uses Hough-circle detection + lattice fitting + per-well disk-mean readout. No deep learning. See `SegOid-chipOid_handoff.md` for background.

## What chipOid does

For each input image: finds the wells, then measures the fluorescence intensity inside each well. The output is one CSV row per well per image, with intensity statistics per fluorescence channel. An optional **inclusion** step flags wells whose fluorescence is in the noise on *every* channel (a well is excluded only when all markers are below their thresholds). That is a noise/occupancy QC, not a cell detector and not a live/dead classifier; excluded wells stay in the outputs, flagged. Beyond that, chipOid does not label wells biologically and does not normalize across images — those are downstream-analysis decisions, not pipeline steps.

## File conventions ("BF + companion")

Every input image is actually **a small group of files**, all the same shape:

- **Brightfield** (BF) — the grayscale "light passing through the chip" image. Used **only for geometry** (finding wells). Filename: `<base>.tif`.
- **Companion** images — one fluorescence image per channel (often called "marker"). Used **only for intensity readout** inside each well. Filename: `<base>_<marker>.tif`.

For a typical 2-channel live/dead assay with green and red markers:

```
data/
├── mcf7_media.tif            ← brightfield  ("BF")
├── mcf7_media_green.tif      ← companion (green channel)
└── mcf7_media_red.tif        ← companion (red channel)
```

The shared `<base>` (here `mcf7_media`) is how chipOid pairs them up. Marker names are user-configurable (`markers:` in the config — rename to `[calcein, pi]`, `[dapi, gfp]`, whatever). The naming rule itself is fixed: `<base>.tif` for BF, `<base>_<marker>.tif` for each companion.

**Requirements:**
- BF and all companions for one image must have **identical shape** (same H × W). chipOid checks and errors out if not.
- BF should be **8-bit**. If yours is higher-bit-depth, either let chipOid convert it via the extraction step (see below) or set Canny thresholds manually (see "Detection parameters" below).
- Companions should stay at their **native dtype** (typically uint16). chipOid never modifies companion pixel values — what's in the file is what gets measured.

## Two ways to feed data into chipOid

**Option A — split files already** (recommended if you have them): set `input.extract_channels.enabled: false`. Each manifest row's `source` column points at the BF file; chipOid looks for `<base>_<marker>.tif` next to it for each companion.

**Option B — multi-page raw TIFFs**: set `input.extract_channels.enabled: true` and tell it which page is which channel. chipOid splits each input into a BF + one companion per marker, writes them to **`output/<image_id>/`** alongside the rest of that image's output (so `data_root` is treated as read-only — the pipeline never writes there), then proceeds as in Option A. The brightfield is always converted to 8-bit (per-image percentile clip [1%, 99%] then linear stretch). Companions are written through at native dtype. Set `output.keep_extracted: false` to delete the split files after readout.

## Pipeline stages

| Stage | What it does | Notes |
|---|---|---|
| 0. (optional) **Extract** | Split a multi-page raw TIFF into BF + one companion per marker | Skipped if your data is already split |
| 1. **Detect** | Canny → `hough_circle` → peaks; candidate well centers from BF | `skimage.transform.hough_circle` |
| 2. **Lattice** | Estimate row/column pitch from nearest-neighbor vectors; predict full grid; snap Hough detections; refit the grid to the snapped detections (least-squares affine) and re-snap; fill misses from lattice. Detected wells keep their exact Hough centre | See "Why a lattice" and "Lattice options" |
| 3. **Readout** | For each well: signal disk + bg annulus per companion; per-well intensity statistics | See `METRICS.md` |
| 4. (optional) **Inclusion** | Flag a well as excluded only if every marker's signal is below its threshold (`included`, `exclude_reason` columns) | Off by default for CLI/YAML; see "Inclusion" below |

All stages run inside a single `chipoid run` invocation, driven by a YAML config and a CSV manifest.

### Why a lattice (and what it forbids)

The lattice is a **geometric backup to Hough**, not a primary detector. After Hough finds the wells it can see, we fit a regular grid (row pitch × col pitch) to those detections and use the grid to fill in any wells Hough missed. The pitches are estimated from the detections themselves — no hard-coded device dimensions.

This is what makes the pipeline robust to dimmer or noisier images: even if Hough misses a few wells, the lattice fills them in at the predicted geometric position.

**The consequence is single-chip-per-image.** chipOid fits ONE lattice per image. If a single image contains two physically separated chips (different lattice origins, or different rotations), the single-lattice fit averages between them, and snapping mislabels which chip each well belongs to. **Split multi-chip images into one chip per image upstream** before running chipOid.

## Desktop GUI

A Tkinter desktop app exposes every pipeline option with inline notes; the window title shows the chipOid version. Two entry points:

```bash
# Launch from a Python install:
chipoid-gui                # console script installed by pyproject
python -m chipoid.gui      # equivalent

# Or build a self-contained Windows .exe:
# See docs/WINDOWS_DESKTOP_BUNDLE.md for the full procedure.
python -m PyInstaller --clean --noconfirm chipoid_gui.spec
```

The GUI builds its config dict and manifest in memory from the input folder
you pick — no intermediate YAML/manifest files are written. Optional
filename parsing splits `<base>` on `_` and assigns user-typed labels to
each chunk, attaching the parsed values as metadata columns on
`wells_all.csv`.

The **Well inclusion (exclude empty wells)** section controls the inclusion step. It is on by default with one shared threshold of 50; untick "Same threshold for all markers" to set one per marker. The **Output** section has a **Write Excel workbook** checkbox (on by default).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quickstart

```bash
chipoid run --config configs/default.yaml
```

This reads `configs/manifest.csv`, processes every image listed, and writes per-image overlays + CSVs into `output/<image_id>/` plus a consolidated `output/wells_all.csv` (and `wells_all.xlsx`) and `output/batch_summary.csv`.

## Manifest

```csv
image_id,source,group,condition,notes
mcf7_media,mcf7_media.tif,A,control,
mcf7_drug,mcf7_drug.tif,A,treated,
```

Columns:
- **`image_id`** (required) — unique identifier; used for output subdirectory and as a column in `wells_all.csv`.
- **`source`** (required) — input file path, resolved under `input.data_root`. When `extract_channels.enabled=false`, this is the BF. When `true`, this is the multi-page raw TIFF.
- **Anything else** — free-form metadata. Every extra column is propagated as-is into the consolidated per-well CSV, so you can filter / group on `condition` etc. in downstream analysis.

## Config

`configs/default.yaml` has the full schema with inline comments. Key blocks:

- **`input.manifest`** — CSV path; one image per row.
- **`input.data_root`** — manifest `source` paths are resolved relative to here.
- **`input.extract_channels.enabled`** — see "Two ways to feed data" above.
- **`markers`** — list of marker (channel) names. Defaults to `[green, red]`.
- **`detection.*`** — Hough/Canny parameters. See below for the bit-depth caveat.
- **`lattice.*`** — pitch and rotation estimation, plus row/col trimming. See "Lattice options" below.
- **`readout.margin / annulus_inner / annulus_outer`** — sampling geometry around each well.
- **`readout.metrics`** — which per-well columns to write. See `METRICS.md`.
- **`inclusion.*`** — optional noise/occupancy QC (`enabled`, `metric`, `min_signal`, `exclude_filled`, `exclude_partial`). See "Inclusion" below.
- **`output.xlsx`** — write `wells_all.xlsx` next to the CSV (default `true`). See "Outputs".

### Lattice options

The lattice fit estimates row/col pitch from the Hough detections, fits a grid to them, and snaps detections to grid points (filling in any wells Hough missed). Key knobs:

- **`lattice.rotation_deg: auto`** (default). The pipeline estimates lattice rotation from the data via a circular mean of nearest-neighbor angles. Override with a numeric value in degrees (e.g. `rotation_deg: 0` to force axis-aligned) if the estimator misbehaves on a difficult image.
- **`lattice.min_detected_fraction: 0.25`** (default). After snapping, any row or column where fewer than this fraction of wells are Hough-detected gets dropped. Catches the failure mode where the lattice bbox extends beyond the actual chip and generates rows of all-filled-no-detected wells. Set to `0` to disable.
- **`lattice.max_rows`** / **`lattice.max_cols`** (default `null`). Optional hard caps applied AFTER the density filter. Use only when you know the chip's true layout — highest-index rows/cols are trimmed first.
- **`lattice.snap_tolerance: 30.0`** (default). Max pixel distance between a predicted grid point and the nearest Hough detection for the well to be considered "detected" rather than "filled".

**Refit.** The rotation and median-pitch fit only seeds the grid indices. chipOid then fits an affine map from (row, col) to (x, y) to the snapped detections by least squares and re-snaps (up to 3 times, one detection per grid point). This matters when the row spacing alternates (e.g. 148/156 px): a median pitch drifts by tens of pixels over a tall chip, while the affine fit uses the mean period and absorbs slight shear. Detected wells keep their exact Hough `x, y, r`; filled wells sit at the fitted grid position, and `col_pitch` / `row_pitch` report the refit geometry.

**Fit quality.** Each image logs `lattice QC: residual median=… p95=… px (refit iterations N, rescued M)`: the distance from detected wells to their fitted grid positions (also `lattice_resid_median` / `lattice_resid_p95` in `batch_summary.csv`). If the median exceeds 0.25 × `r_well` (the median detected radius), it also logs a `[WARN]`; check `03_lattice_overlay.png`.

### Inclusion (optional)

```yaml
inclusion:
  enabled: false        # CLI/YAML default; the GUI turns it on (threshold 50)
  metric: signal        # signal | signal_median
  min_signal: 50        # one number for every marker, or {green: 50, red: 50}
  exclude_filled: false # also exclude lattice-filled wells
  exclude_partial: true # also exclude wells whose signal disk is clipped by the image edge
```

A well is kept if **any** marker's `metric` is at or above that marker's threshold, and excluded only when **every** marker is below. A well with strong red and no green (or the reverse) is therefore kept; a well with neither is excluded. This is a noise/occupancy QC, not a cell detector or a live/dead classifier. A `min_signal` mapping needs an entry for every marker. Thresholds are raw counts after background subtraction, so they depend on exposure and gain: pick them per experiment and use one setting for the whole batch.

Excluded wells are not deleted. With inclusion on, `wells.csv` and `wells_all.csv` gain `included` and `exclude_reason` columns (see `METRICS.md`), the overlays draw excluded wells in grey, and the scatter shows the threshold lines. A missing companion then fails that image (the batch continues). With inclusion off, the CSV columns are the same as in v0.9.

### Detection parameters and bit-depth

The Canny defaults (`canny_low_threshold: null`, `canny_high_threshold: null`) tell `skimage.feature.canny` to use its auto thresholds, which are **10% and 20% of the BF dtype's max value**. For 8-bit input this is fine (thresholds at 25 and 51 of 255). For 16-bit input where the data only uses a small fraction of the range, these defaults sit far outside the actual data and **no edges are found**.

If you skip the extraction step **and** your BF is not 8-bit, you must set Canny thresholds explicitly — pick values inside your image's intensity range. The easiest fix is usually to let chipOid extract for you; the in-pipeline 8-bit conversion is exactly what makes the defaults work.

## Outputs

```
output/
├── <image_id>/
│   ├── brightfield.tif          BF (if extracted; gated by output.keep_extracted)
│   ├── <marker>.tif             one per marker (same gating); e.g. green.tif, red.tif
│   ├── 01_canny.png              edge map
│   ├── 02_hough_overlay.png      detected circles on BF
│   ├── 03_lattice_overlay.png    BF with detected (lime) + filled (magenta) wells; labeled by well_id
│   ├── 04_intensity_<marker>.png BF with filled, semi-transparent disks per well, colored by signal (excluded wells grey)
│   ├── 06_histograms.png         signal distributions per marker (skip via output.save_diagnostics)
│   ├── 07_scatter.png            marker-A vs marker-B per well (same gate; threshold lines when inclusion is on)
│   ├── review.png                composite for quick batch review (lattice + each marker + scatter + hist)
│   ├── hough_centers.csv         raw detections (for debugging)
│   └── wells.csv                 per-image table
├── wells_all.csv                 consolidated batch table (every well, every image)
├── wells_all.xlsx                same data as an Excel workbook (output.xlsx; sheets below)
├── batch_summary.csv             one row per image: counts, pitches, lattice residuals, signal quantiles
└── run.log                       full processing log (first line carries the chipOid version; includes the effective merged config)
```

`wells_all.csv` is the file to point downstream analysis at. See `METRICS.md` for column-by-column definitions.

`wells_all.xlsx` (same stem as `output.consolidated_csv`) has four sheets: `all_wells` (same rows as `wells_all.csv`), `included_wells` (only when inclusion is on: the rows with `included = TRUE`), `summary` (same as `batch_summary.csv`) and `settings` (chipOid version, timestamp and every effective config value, including the input and output paths). Values only, no formulas. If the file is open in Excel when chipOid tries to write it, chipOid logs a `[WARN]` and carries on.

## Further reading

- `METRICS.md` — column definitions for every output file.
- `docs/LIVE_DEAD_GUIDE.md` — one-page guide for lab users running a green/red live/dead experiment (settings, choosing the inclusion threshold).
- `docs/RELEASE_NOTES_v0.10.md` — what changed in v0.10.

## Assumptions / limits (current)

- **Single chip per image.** See "Why a lattice" above.
- **Lattice approximately axis-aligned** with the image axes. Rotation by a few degrees is OK in principle but not stress-tested.
- **Companions must match BF shape** exactly.
- **Hough only.** The optional second detector (template matching) from the handoff sketch is not implemented yet.
