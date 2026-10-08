# Using chipOid for a live/dead chip experiment

A one-page guide for chipOid v0.10 with a green (live) / red (dead) stain.
chipOid finds the wells, measures green and red in each one, and writes the
numbers to CSV and Excel. You still decide what the numbers mean.

## 1. One experiment = one folder = one run

Put every condition of an experiment (media, treatments, kill control) in
**one input folder** and run them together. All conditions then get the same
settings and land in one `wells_all.csv` / `wells_all.xlsx` with an
`image_id` column, so there's nothing to merge by hand.

To get a condition column automatically, name the files consistently, with
underscores between the parts (for example `EXP24_Media.tif`,
`EXP24_TX100.tif`, `EXP24_NCs-laser.tif`). Then tick **Parse filenames into
metadata fields** and type the labels, e.g. `experiment, condition`. Mixing
`-` and `_` as separators (`EXP24-TX100`) gives a different number of parts,
so keep them consistent.

## 2. Settings

- **Extract channels:** on for the microscope's multi-page TIFFs; pages are brightfield 0, green 1, red 2.
- **Detection / Lattice:** as before (radius 35–50, and `max_rows 25`, `max_cols 4` for these chips).
- **Well inclusion (new):** on by default, threshold 50 for every marker. See below. If you set a separate threshold per marker, editing or adding a marker name keeps those values, but clearing the whole markers field and retyping it resets them to the shared value.
- **Write Excel workbook:** on.

## 3. Empty wells and the threshold

An empty well has green and red both in the noise, which makes its %Live
roughly random around 50 %. chipOid now **excludes a well only when every
channel is below its threshold**. A dead well (green low, red high) and a live
well (red low, green high) are both kept. Excluded wells are not deleted: they
stay in `all_wells`, marked `included = FALSE` with an `exclude_reason`.

The threshold is in raw counts after background subtraction, so it depends on
exposure and gain. To choose it:
1. Open the kill control's `07_scatter.png`. Empty wells form a tight cluster near (0, 0). Wells with cells sit far out along red (dead) or green (live).
2. Pick a value between that cluster and the nearest real wells. On the EXP24 data, any value from 50 to 200 gave the same kill-control selection, and 50 worked best across all conditions.
3. Keep that value fixed for the whole experiment. Re-check it if exposure or gain changes.

This is a fluorescence check, not a cell detector. Your brightfield judgement
("are there cells, or is it debris?") is still the reference. Use the figures
to confirm the threshold agrees with what you see.

## 4. Check the result (two minutes per image)

- `review.png`: excluded wells are **grey**. They should be the wells you'd call empty.
- `03_lattice_overlay.png`: **magenta** circles are wells the detector missed, placed from the grid. They should still sit on a trap. `run.log` warns if the grid fit is poor.
- `07_scatter.png`: the dashed lines show the threshold.

## 5. The workbook

`wells_all.xlsx` has these sheets:

| Sheet | Contents |
|---|---|
| `all_wells` | Every well. |
| `included_wells` | Wells with signal; use this one for %Live. |
| `summary` | One row per image (counts, thresholds). |
| `settings` | The chipOid version and every setting used. |

Per well, %Live = `signal_green / (signal_green + signal_red) × 100`.

## 6. Which average to report

- **Mean of per-well %Live:** every well counts the same.
- **Pooled:** Σ green / (Σ green + Σ red); bright wells count more.

The two can differ a lot (EXP24 Media: about 70 % vs 78 %). Pick one, use it
for every condition, and say which one in the methods.

## 7. What chipOid does not do

- **Live/dead classification and control normalisation.** chipOid doesn't classify wells live or dead and doesn't normalise between images. Compute `%NormLive = (x − TX100) / (Media − TX100) × 100` downstream, from your control conditions.
- **Absolute intensity comparison between runs.** Different exposure or illumination changes the raw numbers; compare within an experiment, against its controls.
