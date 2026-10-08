# Handoff — `fix/lattice-refit`

| | |
|---|---|
| Branch | `fix/lattice-refit` |
| Worktree dir | `~/projects/miniProjects/202605_chipOid-wt/lattice-refit/` |
| Base | `main` @ `f993e5e` |
| Created | 2026-10-08 |
| Suggested model / effort | Opus 5.5 / medium |
| Issues | Closes #3 · Refs #12 (duplicate-snap guard) |
| Coordinator session | `main` checkout at `~/projects/miniProjects/202605_chipOid/` |

Read this first, then `CLAUDE.md`, then GitHub issue #3 (`gh issue view 3`).
This directory is a git worktree: it *is* this branch. Do not `git checkout`
another branch here. Machine-specific paths (EXP24 data, baseline outputs,
validation commands) are in `LOCAL_SETUP.md` (gitignored, copied in).

## Goal

Make the lattice fit accurate enough that a well Hough detected is never
"filled" at a grid point 30 px away. On EXP24 TX100, three wells that Hough
found were marked `filled` and read ~30 px off-centre.

Root cause (confirmed, see #3): `estimate_pitches` takes a **median** of
nearest-neighbour vectors. On this chip the spacing between consecutive rows
alternates ~148/156 px, so the median lands 1.5–2.2 px/row off the true mean
period, and over a 25-row chip that drifts ~27 px. An offline least-squares
affine fit on the snapped detections brings the residual to ~3 px on all four
EXP24 images and puts the three TX100 wells within 5–7 px of their detections.
This branch builds that refit into `fit_lattice`.

This is correctness-critical: chipOid's outputs are hard to spot-check by eye,
and the v0.10 empty-well threshold (#1, another branch) will read whatever
position this stage hands it.

## Scope

**In:**
1. Affine refit + re-snap loop inside `fit_lattice` (algorithm below).
2. Unique assignment: one Hough detection can be assigned to at most one grid point (#12).
3. Fill rescue: a grid point left unassigned takes the nearest *unassigned* detection within `default_r`.
4. Detected wells carry their **exact** Hough `x, y, r` (no rotate/de-rotate round trip). Today the round trip turns 207 into 206.99999999999997, which shifts the sampling disk by a few pixels and makes results differ between Linux and Windows.
5. Lattice QC: residual stats in `info`, one log line, a `[WARN]` when the fit is poor, two new `batch_summary.csv` columns.
6. Log a line when `max_rows` / `max_cols` actually cut rows/cols (today it's silent).
7. Tests: new `tests/test_lattice.py`.

**Out** (do not do here):
- `snap_tolerance` relative to `r_well` (#3 proposal 4): not in v0.10; keep the default 30.
- Changing `default_r` / `r_well` (#9).
- Anything in `readout.py`, `viz.py`, `config.py`, the GUI, inclusion or xlsx (other branches).
- `README.md` / `METRICS.md` edits. Write notes in "Notes for the docs pass" instead.

## Contract (fixed; do not change without asking)

- `fit_lattice(centers, image_shape, *, k_nn, axis_band, snap_tolerance, rotation_deg, min_detected_fraction, max_rows, max_cols)`: signature unchanged.
- Returned `wells` columns unchanged: `row, col, x, y, r, source, dist_to_det` (+ `well_id` from renumbering). `source` stays `detected` | `filled`. No new per-well columns.
- `dist_to_det` keeps its meaning: distance from the (refit) predicted grid position to the nearest Hough detection. For detected wells that is the fit residual.
- `info` keeps every existing key and adds:
  - `resid_median`, `resid_p95`: px, over detected wells after trimming (NaN if none).
  - `refit_iterations`: int, 0 when the refit was skipped.
  - `n_rescued`: int, grid points filled by an unassigned detection in step 3.
- After a refit, report the refit geometry in the existing keys: `col_pitch = |b|`, `row_pitch = |a|`, `rotation_deg = degrees(atan2(b_y, b_x))`. Here `a` is (dx, dy) per row step and `b` is (dx, dy) per column step. `rotation_source` still means the source of the initial estimate (`auto` / `manual`).
- `default_r` unchanged (median radius of all Hough detections).
- `pipeline.py`:
  - After the existing `lattice:` log line: `  lattice QC: residual median=4.1 p95=6.5 px (refit iterations 1, rescued 0)`.
  - When `resid_median > 0.25 * r_well`: `  [WARN] lattice residual median 9.7 px > 0.25 × r_well (9.5 px); check 03_lattice_overlay.png`.
  - When caps trimmed something: `    capped rows: kept 25 of 26` (same for cols).
  - `batch_summary.csv`: new columns `lattice_resid_median` and `lattice_resid_p95`, right after `row_pitch`. NaN when the lattice is disabled.
- Lattice-disabled path (`lattice.enabled: false`): behaviour unchanged, and the pipeline must not crash on the missing QC keys.

## Algorithm (fixed)

1. **Initial fit: unchanged.** Rotation estimate, de-rotate, `estimate_pitches`, `estimate_origin`, `generate_grid`, first snap. This seeds the grid indices `(i, j)` and a first assignment.
2. **Refit loop**, at most 3 iterations, in the **original image frame** (an affine absorbs rotation and shear):
   1. From the current assignment, collect pairs `(i, j) ↔ detection (x, y)`.
   2. Stop and keep the current result if there are fewer than 6 pairs, or if the design matrix `[1, i, j]` has rank < 3 (all pairs in one row or one column). `refit_iterations` = iterations done so far.
   3. Least squares: `[x, y] ≈ [1, i, j] @ P`, where `P` is 3×2 (origin, row vector `a`, column vector `b`). Plain LSQ, no weighting.
   4. Index range: map every Hough detection to lattice coordinates with the inverse affine, round, and take `i_min..i_max` and `j_min..j_max`. This mirrors today's "detection bbox ± 0.5 pitch". Spurious detections may add an edge row or column; the density filter removes those, as it does now.
   5. Predict every `(i, j)` in that range and re-snap with **unique assignment**. Take all (grid point, detection) pairs with distance ≤ `snap_tolerance`, sort by distance, and greedily accept a pair if neither side is taken yet.
   6. Stop when the assignment is unchanged from the previous iteration.
3. **Rescue:** each still-unassigned grid point takes the nearest *unassigned* detection within `default_r` (greedy by distance, unique). That well becomes `detected` and counts in `n_rescued`.
4. **Outputs:** detected wells take the detection's exact `x, y, r` from `centers`; filled wells take the predicted position with `r = default_r`. `dist_to_det` as in the contract.
5. **Trim:** `trim_lattice` unchanged, then the existing `info` fields.

If the refit is skipped, still apply unique assignment and the exact-Hough-centre rule to the initial snap.

## Acceptance

**Tests** (`tests/test_lattice.py`, synthetic, no image I/O). Build a 25 × 4 lattice with:
- row spacing alternating 148/156 px and column pitch ~205 px;
- the column axis rotated ~0.7° and the row axis ~0.9° (slight shear);
- origin ~(220, 130), 1 px Gaussian jitter, a fixed seed, and radii alternating 38/44.

Checks:
- [ ] Drop 3 detections in the top rows. Expect 100 wells: those 3 `filled` and within 3 px of truth, everything else `detected`, and `resid_median` < 3 px. Confirm the old code fails this case (filled wells > 20 px off) and keep it as a regression test.
- [ ] Detected wells' `x, y, r` are exactly the input Hough values (`==`, not approx).
- [ ] Unique assignment: a detection equidistant from two grid points (tight synthetic pitch, e.g. 50 px with tolerance 30) goes to only one of them. The other is `filled` or rescued, never both from the same detection.
- [ ] A spurious detection one row above the chip (like a printed row label) gets trimmed, and the well count is unchanged.
- [ ] A perfect axis-aligned lattice gives the same well_ids and positions as before (all detected, residual ~0).
- [ ] Degenerate input (≤ 5 detections, or all in one row) doesn't crash, and `refit_iterations == 0`.
- [ ] Full suite green; record the count (baseline 41).

**EXP24.** Commands are in `LOCAL_SETUP.md`. Use run name `lattice_refit`, so `output.dir` = `.../output/v010_validation/lattice_refit`. Run `scripts/validate_exp.py --run $V/lattice_refit --baseline $V/baseline_v0.9 --picks $V/exp24_handpicks.csv --thresholds 50,100` and paste the tables into the PR:
- [ ] TX100: 100 wells, 100 detected, 0 filled; residual median < 5 px.
- [ ] Media, Media + laser, NCs + laser: still 100 detected / 0 filled; residual medians ≈ 3 px.
- [ ] "source changed" lists only the 3 TX100 wells, and max |dx|, |dy| < 1e-6 px for wells detected in both runs.
- [ ] Metric changes appear only on those 3 wells, plus at most the 7 TX100 wells where the round-off disappears (|Δ signal| ≤ 0.5).
- [ ] TX100 vs picks at `max ≥ 50`: expect 100/100. The one disagreement in the baseline was a misplaced filled well.
- [ ] `03_lattice_overlay.png` for TX100: no magenta wells, and circles centred on the traps.

## Conflict watchlist

- `src/chipoid/pipeline.py`: `feat/inclusion-xlsx` changes `process_image` (readout loop, summary dict, per-image CSV write) and `run_batch_in_memory` (first log line, consolidated output). Keep your edits to the lattice log lines and the `summary` dict entries listed above. Expect at most a trivial conflict in the summary dict.
- `tests/`: add a new file only.

## Status

- [x] Algorithm implemented
- [x] Unit tests (`tests/test_lattice.py`, 7 tests; suite 48 passed, baseline 41)
- [x] EXP24 acceptance tables (in the PR; run `output/v010_validation/lattice_refit`)
- [x] PR open

Deviations / findings (details in the PR):
- **Metric changes are wider than predicted.** Exact Hough centres remove the
  rotate/de-rotate round-off on 15–37 wells per image (not just the 7 TX100
  wells), changing `signal_*` by ≤ 1.9 counts (not ≤ 0.5). Cause: integer
  centres + integer radii put rim pixels exactly on the disk boundary, so a
  1e-14 px shift flips them. Lab Windows outputs carry the same round-off as
  the Linux baseline, so this is a one-time shift towards exact geometry.
- **TX100 vs picks at max ≥ 50: 99/100, not 100/100.** The disagreement is
  r00c02, now read on its real well (was a misplaced filled well); BF shows a
  spheroid in it, it reads red ≈ 204, and it is not in the 19 picks.
- **Regression test:** on the synthetic fixture the v0.9 code puts the 3
  filled wells 10–15 px off (the brief expected > 20 px). The balanced 148/156
  spacing lets the median land near 153 px rather than 155 as on EXP24. It
  still fails the < 3 px check, so the test is a valid regression test.
- **Pre-existing crash fixed in `_renumber_and_label`:** whenever a
  `max_rows`/`max_cols` cap actually fired, the next renumber re-inserted
  `well_id` and raised `ValueError`. Needed for the capped-rows log line;
  `trim_lattice` behaviour is otherwise unchanged. It now also reports
  `capped_rows_total` / `capped_cols_total` (for "kept 25 of 26").
- `estimate_pitches` clamps k to the number of points (crashed with < 5
  detections); NaN pitches (one row/col) borrow the other pitch.
- `x0`, `y0` in `info` stay the initial working-frame origin (not the refit
  origin); `n_grid` is the final grid size.

## Notes for the docs pass

- **Refit (README "Lattice options"):** the rotation + median-pitch fit only
  seeds grid indices; chipOid then fits an affine map (row, col) → (x, y) by
  least squares to the snapped detections and re-snaps (≤ 3 iterations, unique
  one-to-one assignment, then unassigned grid points take an unused detection
  within `r_well`). This uses the mean row period and absorbs slight shear.
- **METRICS.md:** `batch_summary.csv` gains `lattice_resid_median`,
  `lattice_resid_p95` (px, detected wells after trim; NaN if lattice disabled).
  `run.log` gains `lattice QC: residual median=… p95=… px (refit iterations N,
  rescued M)`, a `[WARN]` when median > 0.25 × r_well, and `capped rows/cols:
  kept K of N`. `col_pitch`/`row_pitch`/rotation now report the refit geometry.
- **dist_to_det:** distance from the refit grid position to the assigned
  detection (detected wells, i.e. the fit residual) or to the nearest
  detection (filled wells). Never 0 for filled wells.
- Detected wells' `x, y, r` are now the exact Hough values (integers in
  practice); signal disks no longer depend on float round-off.
- README "circular-median" → circular mean.

<!-- Fill in:
     - how the refit works, in two sentences (README "Lattice options");
     - the new batch_summary columns and log lines (METRICS.md);
     - the dist_to_det definition fix (METRICS.md says "0 for filled wells",
       which was never true).
     Also: README calls the rotation estimate a "circular-median"; it is a
     circular mean. -->

## Questions for the coordinator

- TX100 r00c02 (spheroid visible, red ≈ 204) is now kept at T = 50 but is not
  in the hand-picks. Was it left out because v0.9 read it off-centre? If it
  should be a pick, the 100/100 criterion holds.
- With a spurious row at the *top* that the density filter keeps (e.g. a
  label exactly on a grid point), `max_rows` still cuts the bottom real row
  (#12 observation). Not changed here; the new log line makes it visible.

## Return protocol

1. Keep **Status** current; note any deviation from this brief.
2. `pytest tests/` passes; record the count against the baseline (41).
3. `git fetch origin && git rebase origin/main`, then re-run the tests.
4. Push the branch and open a PR against `main` with `Closes #3` and `Refs #12`. PR body = the review packet: what changed and why, deviations from the brief, test counts, the EXP24 tables, and any pre-existing bug you noticed but did not fix.
5. Tell the human the PR is up. The coordinator spot-checks and merges (this one first).
