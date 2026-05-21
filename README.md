# chipOid

Classical-CV well detector + fluorescence readout for microfluidic chip overview images.

The problem here is geometric (find wells on a lattice, read fluorescence), not biological — so chipOid uses Hough-circle detection + lattice fitting + per-well disk-mean readout. No deep learning. See `SegOid-chipOid_handoff.md` for background.

## What chipOid does

For each input image: finds the wells, then measures the fluorescence intensity inside each well. The output is one CSV row per well per image, with intensity statistics per fluorescence channel. That's it — chipOid does not classify wells, does not threshold biology, and does not normalize across images. Those are downstream-analysis decisions, not pipeline steps.

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
| 2. **Lattice** | Estimate row/column pitch from nearest-neighbor vectors; predict full grid; snap Hough detections; fill misses from lattice | See "Why a lattice" below |
| 3. **Readout** | For each well: signal disk + bg annulus per companion; per-well intensity statistics | See `METRICS.md` |

All stages run inside a single `chipoid run` invocation, driven by a YAML config and a CSV manifest.

### Why a lattice (and what it forbids)

The lattice is a **geometric backup to Hough**, not a primary detector. After Hough finds the wells it can see, we fit a regular grid (row pitch × col pitch) to those detections and use the grid to fill in any wells Hough missed. The pitches are estimated from the detections themselves — no hard-coded device dimensions.

This is what makes the pipeline robust to dimmer or noisier images: even if Hough misses a few wells, the lattice fills them in at the predicted geometric position.

**The consequence is single-chip-per-image.** chipOid fits ONE lattice per image. If a single image contains two physically separated chips (different lattice origins, or different rotations), the single-lattice fit averages between them, and snapping mislabels which chip each well belongs to. **Split multi-chip images into one chip per image upstream** before running chipOid.

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

This reads `configs/manifest.csv`, processes every image listed, and writes per-image overlays + CSVs into `output/<image_id>/` plus a consolidated `output/wells_all.csv` and `output/batch_summary.csv`.

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

### Lattice options

The lattice fit estimates row/col pitch from the Hough detections, fits a grid to them, and snaps detections to grid points (filling in any wells Hough missed). Key knobs:

- **`lattice.rotation_deg: auto`** (default). The pipeline estimates lattice rotation from the data via a robust circular-median of nearest-neighbor angles. Override with a numeric value in degrees (e.g. `rotation_deg: 0` to force axis-aligned) if the estimator misbehaves on a difficult image.
- **`lattice.min_detected_fraction: 0.25`** (default). After snapping, any row or column where fewer than this fraction of wells are Hough-detected gets dropped. Catches the failure mode where the lattice bbox extends beyond the actual chip and generates rows of all-filled-no-detected wells. Set to `0` to disable.
- **`lattice.max_rows`** / **`lattice.max_cols`** (default `null`). Optional hard caps applied AFTER the density filter. Use only when you know the chip's true layout — highest-index rows/cols are trimmed first.
- **`lattice.snap_tolerance: 30.0`** (default). Max pixel distance between a predicted grid point and the nearest Hough detection for the well to be considered "detected" rather than "filled".

### Detection parameters and bit-depth

The Canny defaults (`canny_low_threshold: null`, `canny_high_threshold: null`) tell `skimage.feature.canny` to use its auto thresholds, which are **10% and 20% of the BF dtype's max value**. For 8-bit input this is fine (thresholds at 25 and 51 of 255). For 16-bit input where the data only uses a small fraction of the range, these defaults sit far outside the actual data and **no edges are found**.

If you skip the extraction step **and** your BF is not 8-bit, you must set Canny thresholds explicitly — pick values inside your image's intensity range. The easiest fix is usually to let chipOid extract for you; the in-pipeline 8-bit conversion is exactly what makes the defaults work.

## Outputs

```
output/
├── <image_id>/
│   ├── <image_id>.tif            BF (if extracted; gated by output.keep_extracted)
│   ├── <image_id>_<marker>.tif   one per marker (same gating)
│   ├── 01_canny.png              edge map
│   ├── 02_hough_overlay.png      detected circles on BF
│   ├── 03_lattice_overlay.png    BF with detected (lime) + filled (magenta) wells; labeled by well_id
│   ├── 04_intensity_<marker>.png BF with filled, semi-transparent disks per well, colored by signal
│   ├── 06_histograms.png         signal distributions per marker (skip via output.save_diagnostics)
│   ├── 07_scatter.png            marker-A vs marker-B per well (same gate)
│   ├── review.png                composite for quick batch review (lattice + each marker + scatter + hist)
│   ├── hough_centers.csv         raw detections (for debugging)
│   └── wells.csv                 per-image table
├── wells_all.csv                 consolidated batch table (every well, every image)
├── batch_summary.csv             one row per image: counts, pitches, rotation, signal quantiles
└── run.log                       full processing log (includes the effective merged config)
```

`wells_all.csv` is the file to point downstream analysis at. See `METRICS.md` for column-by-column definitions.

## Assumptions / limits (current)

- **Single chip per image.** See "Why a lattice" above.
- **Lattice approximately axis-aligned** with the image axes. Rotation by a few degrees is OK in principle but not stress-tested.
- **Companions must match BF shape** exactly.
- **Hough only.** The optional second detector (template matching) from the handoff sketch is not implemented yet.
