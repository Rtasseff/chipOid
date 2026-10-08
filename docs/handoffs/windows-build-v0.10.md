> **Done 2026-10-08.** The build passed. P1 and P2 were fixed in #17 and #18, and the rebuild brief is `windows-rebuild-v0.10.x.md`.

# Handoff — Windows build of chipOid v0.10.0

| | |
|---|---|
| Session | Windows Claude Code session on the main checkout via the WSL share |
| Build commit | `main` at or after `9635831` (version `0.10.0`) — see step 1 |
| Created | 2026-10-08 |
| Issues | #5 (rebuild + smoke test) |
| Coordinator session | WSL, `~/projects/miniProjects/202605_chipOid/` |

Read `docs/WINDOWS_SESSION.md` first: it has the rules (git read-only, no
edits to tracked files, report here) and the standard procedure. Concrete
paths are in `LOCAL_SETUP.md`. The build steps and the generic smoke tests are
in `docs/WINDOWS_DESKTOP_BUNDLE.md`.

## Goal

Build `chipOid.exe` for v0.10.0, prove it works on Windows (including the new
empty-well exclusion and the Excel workbook), check that it gives the same
numbers as the coordinator's Linux run, and package it for the human to hand
to the lab.

## Steps

1. **Preflight.**
   - `git log --oneline -3`: HEAD is `9635831` or a later docs-only commit.
   - Confirm the code is the validated code: `git diff --stat 9635831 HEAD -- src chipoid_gui.spec requirements.txt pyproject.toml` prints nothing. (The Linux reference run was made at `55d489a`; `9635831` differs from it only by a comment in `config.py`.)
   - Record `git status`; noise is expected.
2. **Build venv.** `.venv-build\Scripts\python -m pip install -r requirements.txt pyinstaller pytest pillow`. Confirm `openpyxl` is now installed (`pip show openpyxl`).
3. **Unit tests on Windows.** Run `$env:PYTHONPATH = "src"`, then `.venv-build\Scripts\python -m pytest tests -q`.
   - Expect **113 passed**.
   - If the `test_pipeline_in_memory.py` tests skip, the `data\` symlink didn't resolve from Windows. Note it and carry on; those tests ran in WSL.
4. **Build** with `--distpath D:\projects\chipOid\dist --workpath D:\projects\chipOid\build` (`docs/WINDOWS_SESSION.md`, step 4). Record the build time, the `.exe` size, and any PyInstaller warnings that mention `chipoid`, `openpyxl` or `imagecodecs`.
5. **Generic smoke tests 1–9** from `docs/WINDOWS_DESKTOP_BUNDLE.md`.
   - The title must read **`chipOid v0.10.0`**.
   - The new "Well inclusion" section has **only been compile-checked so far** (WSL has no Tk), so test 3 (defaults, per-marker fields, marker edits) is the first real check of that code. Be thorough there.
   - For tests 4–7, use the EXP24 run below.
6. **EXP24 run in the GUI** (also the cross-platform check).
   - **Input.** Copy the four raw TIFFs into one folder, `C:\Users\<you>\chipoid_smoke\exp24_in\`. They're in the four `ChipOid_<cond>\` folders under the EXP24 path in `LOCAL_SETUP.md`: `EXP24_Media.tif`, `EXP24_Laser_media.tif`, `EXP24_NCs-laser.tif`, `EXP24-TX100.tif`.
   - **GUI settings:**
     - Input = that folder; Output = `C:\Users\<you>\chipoid_smoke\exp24_out\`.
     - Extract channels **on**: brightfield page 0, green 1, red 2.
     - radius_min 35, radius_max 50, max_rows 25, max_cols 4.
     - Everything else at its default (exclusion on, threshold 50 for all markers). No filename parsing.
   - **Expected** (coordinator's Linux run of `55d489a`, in `D:\projects\chipOid\output\v010_validation\rc_linux`):

     | image | wells | detected | filled | included |
     |---|---|---|---|---|
     | EXP24_Media | 100 | 100 | 0 | 91 |
     | EXP24_Laser_media | 100 | 100 | 0 | 96 |
     | EXP24_NCs-laser | 100 | 100 | 0 | 95 |
     | EXP24-TX100 | 100 | 100 | 0 | 20 |

     `run.log` should show `lattice QC: residual median=` 2.5–3.2 px for each image, and no `[WARN]` lines.
   - **Compare:**
     ```powershell
     .venv-build\Scripts\python scripts\validate_exp.py `
       --run C:\Users\<you>\chipoid_smoke\exp24_out `
       --baseline D:\projects\chipOid\output\v010_validation\rc_linux
     ```
     Expect "source changed: none", max |dx|, |dy| = 0, and **zero** wells with metric changes. v0.10 keeps exact Hough centres, so Windows and Linux should now agree exactly. "Columns only in baseline: condition" is expected (the Linux manifest has a condition column). Paste the tables in the Report.
   - **Figures.** In `EXP24-TX100\review.png`, 80 wells are grey and 20 are coloured. In `EXP24-TX100\03_lattice_overlay.png`, there are no magenta circles.
7. **Package.**
   - Copy the `.exe` to `D:\projects\chipOid\dist\chipOid_v0.10.0.exe`.
   - Copy `docs\RELEASE_NOTES_v0.10.md` and `docs\LIVE_DEAD_GUIDE.md` next to it.

## Report

Windows session, 2026-10-08. **Verdict: the `.exe` is good to ship.**
- All EXP24 numbers match the Linux run exactly.
- Every smoke test that can run on a locked screen passed (see the note under smoke tests).
- One code problem is worth fixing: P1, the matplotlib backend. It did not affect the `.exe` in any run here.

### Commit built
- `ecff281` on `main`, a docs-only commit after `9635831`.
- `git diff --stat 9635831 HEAD -- src chipoid_gui.spec requirements.txt pyproject.toml` prints nothing.
- `git status` is clean. Git was run read-only through `wsl.exe`, which avoids Git-for-Windows noise.
- `__version__ = "0.10.0"`.

### Python / PyInstaller versions
- Python 3.13.14 (Microsoft Store), PyInstaller 6.20.0.
- numpy 2.4.6, pandas 3.0.3, scikit-image 0.26.0, scipy 1.17.1, matplotlib 3.10.9.
- tifffile 2026.5.15, imagecodecs 2026.5.10, openpyxl 3.1.5 (newly installed).

### Unit tests
- `pytest tests -q` from the repo: **105 passed, 8 skipped**. The skips are all of `test_pipeline_in_memory.py`, because the `data\` symlink doesn't resolve from Windows, as anticipated.
- To cover those 8 on Windows, I re-ran that file from a scratch folder where `data` is a junction to `D:\projects\chipOid\data`: **7 passed, 1 failed** (`test_inclusion_off_adds_nothing`). It failed in 2 of 2 full-file runs and passes when run alone. This is a Windows/dev-environment problem, not chipOid logic. See P1.

### Build
- **Time:** 686 s (~11.4 min) over the WSL share.
- **Size:** `chipOid.exe` is 148,358,436 bytes (141.5 MiB). SHA-256 `7ef9f5c65978dbf7e2d1a9437a25f6a50dc54ad57f2061638ec67d08edcb85c3`.
- **Warnings:** 9 in total; none mention `chipoid` or `openpyxl`. The four that mention `imagecodecs` are optional codec DLLs that aren't shipped (`jxs.dll`, `dpcore.dll`, `jetraw.dll`, `heif.dll`, for JPEG-XS, Jetraw and HEIF). They're not needed for TIFF. The other five are harmless:
  - no `numba`;
  - no `torch`;
  - no matplotlib test images;
  - no Qt bindings;
  - the hidden import `scipy.special._cdflib` was not found.
- Full log: `C:\Users\<you>\chipoid_smoke\build_v0.10.0.log`.

### Smoke tests 1–9

**Method note.** The PC was **locked** for this whole session, so there was no real mouse and no screen capture. The `.exe` was:
- launched through `explorer.exe`;
- captured with `PrintWindow`;
- driven **by keyboard only**, with Tab traversal and keystrokes posted as window messages.

Tk ignores posted mouse clicks: a ttk button checks the real pointer position on release. The Tab order was taken from the same source built in-process. Every setting typed into the `.exe` was then confirmed in `run.log`'s effective config.

| # | Test | Result | Notes |
|---|---|---|---|
| 1 | Launch | **PASS** | Launched from Explorer. The window appeared in 5.5–6.6 s, titled `chipOid v0.10.0`. |
| 2 | Scroll / sections | **PARTIAL** | The top sections render correctly. The mouse wheel and scroll bar **can't be tested on a locked screen**, and the lower sections are off-screen: Windows caps the window height at 1100 px. That the lower sections exist and work is shown by tests 3, 4 and 8. *To do on an unlocked PC (1 min): scroll down and look at "Well inclusion" and "Output".* |
| 3 | Well-inclusion defaults | **PASS (logic) / visual pending** | See the two parts below. |
| 4 | Small run | **PASS** | The 4-image EXP24 run took about 42 s. The log streamed live in the window. Status: `Done. 4/4 images succeeded`. Output has `wells_all.csv`, `batch_summary.csv`, `wells_all.xlsx`, `run.log` and 4 per-image folders. |
| 5 | Workbook | **PASS** | Opened in Excel (COM). Sheets: `all_wells`, `included_wells`, `summary`, `settings`. `included_wells` has 302 rows against 400 in `all_wells`. `settings` shows `chipoid_version = 0.10.0`, so openpyxl is bundled. |
| 6 | Excluded wells in figures | **PASS** | TX100 `review.png`: 80 wells grey, 20 coloured, legend "excluded (80) / included (20)". `04_intensity_red.png`: excluded wells grey. `07_scatter.png`: dashed threshold lines at 50/50. |
| 7 | Files open in Excel | **PASS** | With `wells_all.xlsx` and `.csv` locked (opened for editing in Excel), the re-run finished with `Done. 4/4 images succeeded`. Two lines: `[WARN] could not write wells_all.csv (is it open in Excel?)` and the same for `.xlsx`. `batch_summary.csv`, `run.log` and the per-image outputs were rewritten. The locked files were left alone. |
| 8 | Filename parsing | **PASS** | `EXP24_Media.tif` + `EXP24_TX100.tif`, labels `experiment, condition`. `wells_all.csv` has `experiment` = EXP24 and `condition` = Media / TX100, filled in for all 200 rows. |
| 9 | Bad input | **PASS** | Empty input folder → dialog "No brightfield TIFFs found in …\empty_in. Expected <base>.tif files (with optional <base>_<marker>.tif companions)." before the job starts. Nothing was written to the output folder. |

Test 3 in detail:
- **In the `.exe`:** I unticked "same for all" and set green 60 / red 70. `run.log` showed `min_signal: {green: 60.0, red: 70.0}` and `green ≥ 60, red ≥ 70`, so the per-marker fields exist, accept input, and reach the pipeline.
- **In-process (same source, real widgets driven as a user would), 25/26 checks pass:**
  - The defaults are right: exclusion on, "same" on with 50, exclude-filled off, exclude-clipped on, xlsx on.
  - Unticking "same" hides the shared field and shows one field per marker (green, red), seeded with 50.
  - Appending `, blue` to markers gives 3 fields and keeps green 60 / red 70; the new field starts at 50.
  - Renaming the markers to `calcein, pi` makes the fields follow.
  - Re-ticking "same" restores the shared field.
  - Unticking "Exclude empty wells" greys out the sub-options.
  - The one failure is the minor P2.
- **Still to do:** the visual check in the `.exe` itself, together with test 2.

### EXP24 run (step 6): the cross-platform check
Settings were exactly as the brief says. Input `C:\Users\<you>\chipoid_smoke\exp24_in` (4 raw TIFFs), output `…\exp24_out`. `run.log` has **no `[WARN]` lines** in the first run.

| image | wells | detected | filled | included | lattice QC residual median / p95 (px) |
|---|---|---|---|---|---|
| EXP24_Media | 100 | 100 | 0 | 91 | 3.1 / 6.3 |
| EXP24_Laser_media | 100 | 100 | 0 | 96 | 2.5 / 5.0 |
| EXP24_NCs-laser | 100 | 100 | 0 | 95 | 3.1 / 5.2 |
| EXP24-TX100 | 100 | 100 | 0 | 20 | 3.2 / 6.1 |

`validate_exp.py --run …\exp24_out --baseline D:\projects\chipOid\output\v010_validation\rc_linux`:

Columns only in run: none · only in baseline: ['condition'] (expected)

| image | wells (run/base) | source changed | max abs dx, dy (px) | wells with any metric change | max abs d signal_* |
|---|---|---|---|---|---|
| EXP24-TX100 | 100/100 | none | 0, 0 | 0 | 0 |
| EXP24_Laser_media | 100/100 | none | 0, 0 | 0 | 0 |
| EXP24_Media | 100/100 | none | 0, 0 | 0 | 0 |
| EXP24_NCs-laser | 100/100 | none | 0, 0 | 0 | 0 |

Green fraction, as n / mean of per-well % / pooled Σ %:

| image | all wells | included (run) | T = 25 | T = 50 | T = 100 | T = 200 |
|---|---|---|---|---|---|---|
| EXP24-TX100 | 100 / 48.9 / 3.5 | 20 / 2.6 / 2.1 | 23 / 4.8 / 2.2 | 20 / 2.6 / 2.1 | 20 / 2.6 / 2.1 | 20 / 2.6 / 2.1 |
| EXP24_Laser_media | 100 / 66.2 / 68.4 | 96 / 65.9 / 68.4 | 96 / 65.9 / 68.4 | 96 / 65.9 / 68.4 | 95 / 66.4 / 68.5 | 92 / 67.5 / 68.7 |
| EXP24_Media | 100 / 70.3 / 78.5 | 91 / 72.6 / 78.6 | 95 / 71.2 / 78.5 | 91 / 72.6 / 78.6 | 85 / 75.3 / 79.0 | 81 / 77.1 / 79.5 |
| EXP24_NCs-laser | 100 / 59.1 / 67.7 | 95 / 60.1 / 67.8 | 98 / 59.2 / 67.8 | 95 / 60.1 / 67.8 | 92 / 61.3 / 68.0 | 84 / 65.3 / 69.0 |

Figures:
- `EXP24-TX100\review.png` has 80 grey and 20 coloured wells.
- `EXP24-TX100\03_lattice_overlay.png` is titled "100 detected + 0 filled". The only magenta is the legend swatch. The top-row wells (the v0.9 bug) sit on the traps.

### Problems found

**P1 (should fix): matplotlib falls back to TkAgg on Windows. No code selects Agg.**
- **Command:** from `C:\Users\<you>\chipoid_smoke\pytest_cwd`, with `data` as a junction to `D:\projects\chipOid\data`:
  `$env:PYTHONPATH="<repo>\src"; .venv-build\Scripts\python -m pytest <repo>\tests\test_pipeline_in_memory.py -q`
- **Result:** `test_inclusion_off_adds_nothing` fails with `assert result["n_failed"] == 0`. Its `run.log`:
  ```
  [ERROR] mcf7_media: TclError("Can't find a usable tk.tcl in the following directories: ...
  ...tcl/tk8.6/tk.tcl: couldn't read file ".../tcl/tk8.6/panedwindow.tcl": no such file or directory ...")
    File "...src\chipoid\pipeline.py", line 235, in process_image
      viz.save_intensity_overlay(
    File "...src\chipoid\viz.py", line 150, in save_intensity_overlay
      fig, ax = plt.subplots(figsize=_figsize_for(bf.shape))
    File "...matplotlib\pyplot.py", line 551, in new_figure_manager
      return _get_backend_mod().new_figure_manager(*args, **kwargs)
  ```
  The file it can't read does exist. It's an intermittent Tk start-up failure in the Microsoft Store Python.
- **Diagnosis:** nothing in `src/` calls `matplotlib.use("Agg")`; the spec comment says "we never use an interactive backend", but the code doesn't enforce it.
  - On WSL there's no display, so matplotlib silently uses Agg, which is why this never showed up there.
  - On Windows it picks **TkAgg**, so every figure creates a Tk interpreter and window just to save a PNG.
  - In the GUI, those figures are made on the worker thread. Tk off the main thread is unsupported.
  - It didn't fail in any `.exe` run here (3 runs, 10 images, every figure written), but it is a latent crash risk.
- **Proposed fix** (`src/chipoid/viz.py`; must come before the pyplot import):
  ```diff
   from pathlib import Path

  +import matplotlib
  +matplotlib.use("Agg")  # files only; never an interactive backend (TkAgg breaks off the main thread on Windows)
   import matplotlib.patches as mpatches
   import matplotlib.patheffects as mpe
   import matplotlib.pyplot as plt
  ```
  Then rebuild, and re-run `test_pipeline_in_memory.py` on Windows with the junction trick above.

**P2 (minor, cosmetic):** per-marker threshold fields created while "Exclude empty wells" is off are **not** greyed out like the rest of the section.
- **To reproduce:** untick "Exclude empty wells", untick "same for all", then add a marker.
- **Cause:** `_rebuild_min_signal_entries` doesn't re-apply the disabled state.
- **Fix:** at the end of `_rebuild_min_signal_entries`, call `self._on_inclusion_toggle(self.inclusion_enabled.get())`.

**P3 (note, probably fine):** clearing the whole markers field and retyping it resets the per-marker thresholds to the shared value, because each keystroke rebuilds the fields. Appending or editing a marker keeps the values. Maybe one line in the guide.

**P4 (process):** the build takes ~11 min over the WSL share, against the 2–4 min in `WINDOWS_DESKTOP_BUNDLE.md`. Not a problem, but the doc could say "10+ min over the share".

**Open (needs an unlocked PC, about 2 min):** smoke test 2 (mouse wheel / scroll bar) and a visual look at the "Well inclusion" and "Output" sections in the `.exe`.

### Packaged files
In `D:\projects\chipOid\dist\`:
- `chipOid_v0.10.0.exe`: 148,358,436 bytes, identical to `chipOid.exe` (same SHA-256 as above);
- `RELEASE_NOTES_v0.10.md`;
- `LIVE_DEAD_GUIDE.md`.

Scratch (not in the repo): `C:\Users\<you>\chipoid_smoke\` has:
- the EXP24 run (`exp24_out\`) and its validation report (`validate_exp24.md`);
- the test 8 run (`t8_out\`);
- the build log;
- screenshots (`shots\`).
