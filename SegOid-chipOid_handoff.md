# SegOid → chipOid handoff

**Date:** 2026-05-18
**Outcome:** SegOid's production model does not transfer to microfluidic-trap data. Recommend a small standalone classical-CV project for well detection + fluorescence readout. **Do not extend SegOid for this.**

---

## Source dataset characteristics

| Property | Value |
|---|---|
| Files | multi-page TIFFs, 3 pages each |
| Page contents | page 0 = brightfield, page 1 = green fluorophore (live), page 2 = red fluorophore (dead) |
| Pixel size | 3.87 µm/px (5x objective) |
| Bit depth | uint16, 12-bit range (0-4095) |
| Format | tile-stitched microfluidic chip overviews |
| Sizes | smaller files: ~5400×900 px; larger files: ~4500×14000 px |

Pixel size is reliably extractable from CZI metadata (`Scaling|Distance|Value`); the TIFF `XResolution` tag agrees.

---

## Why SegOid fails on this data

- **Training data:** big isolated spheroids in U-bottom wells; the spheroid is the dominant feature; characteristic dark meniscus ring around each well.
- **Microfluidic-trap data:** small spheroids inside circular traps in a microfluidic device; **device geometry dominates the image** (channels, walls, traps); spheroids are subordinate.

The model never saw "spheroid in a microfluidic trap" in training. Transfer learning might recover some of this, but the geometric problem is so much easier than the biological one that retraining is the wrong tool.

---

## Recommended approach: classical-CV well reader

The reframing: **find the wells, then read fluorescence inside them.** No segmentation of contents needed.

### Why this is easy

1. Wells are device features — fixed circular shape, fixed size, manufactured to spec.
2. Wells lie on a regular lattice — once you find several, you know where the rest are.
3. The fluorescence readout is one `mean()` call per well.

### Pipeline sketch

1. **Estimate well radius.** Either user-supplied (one click on an example well), known device spec, or scale-space search on a small ROI.
2. **Detect candidate wells.** Two complementary tools, run together for robustness:
   - `skimage.transform.hough_circle` — direct geometric detection.
   - `skimage.feature.match_template` with a synthetic or extracted template — robust when wells are uniform.
3. **Fit a lattice.** From the autocorrelation of detected centers (or RANSAC on nearest-neighbor vectors), estimate row/column pitch and orientation. Generate the full predicted grid. Then snap each detected center to the nearest lattice point — fills missed detections and rejects spurious ones.
4. **Handle unknown layout.** Cluster lattice points by spatial proximity before fitting — each cluster becomes a separate chip. Crop a channel-area mask from the brightfield (simple thresholding) to discard predicted wells outside the channel.
5. **Per-well intensity readout.** For each well, take a disk of `radius - margin` pixels and compute `mean()` on the green and red companion images. Output CSV: `well_id, chip_id, x, y, mean_green, mean_red`.
6. **Optional live/dead classification.** Threshold on green/red ratio or absolute intensities. If neg/pos control wells exist, calibrate from those.

### Practical notes

- Keep fluorescence channels as 16-bit when computing mean intensity — don't pre-stretch them.
- Brightfield → 8-bit + percentile clip is fine for well detection (only used for geometry).
- All source TIFFs share the same imaging convention, so one script handles all.
- The smaller overview files are the right prototyping targets; the larger ones are the same problem.
- **Do not use deep learning here.** The problem is geometric, not biological.

### What this new project should NOT inherit from SegOid

- The model, the inference pipeline, the manifest schema, the training infrastructure — none of it applies.
- The companion-image convention (`<base>_<marker>.tif`) is useful and worth reusing, but it's just a naming convention, not a code dependency.
