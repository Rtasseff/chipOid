# Handoff — Windows build of chipOid v0.10.0

| | |
|---|---|
| Session | Windows Claude Code session on the main checkout via the WSL share |
| Build commit | `main` at or after `55d489a` (version `0.10.0`) — see step 1 |
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
   - `git log --oneline -3`: HEAD is `55d489a` or a later docs-only commit.
   - Confirm the code is the validated code: `git diff --stat 55d489a HEAD -- src chipoid_gui.spec requirements.txt pyproject.toml` prints nothing.
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

<!-- Windows session: fill this in. -->

- Commit built:
- Python / PyInstaller versions:
- Unit tests:
- Build: time, `.exe` size, notable warnings:
- Smoke tests 1–9 (pass/fail + notes):
- EXP24 run: counts, validation tables:
- Problems found (command, traceback, diagnosis, proposed fix):
- Packaged files:
