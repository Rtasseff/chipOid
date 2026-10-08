# Handoff — Windows build of chipOid v0.10.0

> **DRAFT.** Not ready until the coordinator fills in the commit and the
> expected numbers (marked ⟨…⟩) and commits this file on `main`.

| | |
|---|---|
| Session | Windows Claude Code session on the main checkout via the WSL share |
| Build commit | `main` @ ⟨sha⟩ (version `0.10.0`) |
| Created | 2026-10-08 |
| Issues | #5 (rebuild + smoke test) |
| Coordinator session | WSL, `~/projects/miniProjects/202605_chipOid/` |

Read `docs/WINDOWS_SESSION.md` first: it has the rules (git read-only, no
edits to tracked files, report here) and the standard procedure. Concrete
paths are in `LOCAL_SETUP.md`. The build steps and the generic smoke tests are
in `docs/WINDOWS_DESKTOP_BUNDLE.md`.

## Goal

Build `chipOid.exe` for v0.10.0 from the commit above, prove it works on
Windows (including the new empty-well exclusion and the Excel workbook), check
that it gives the same numbers as the coordinator's Linux run, and package it
for the human to hand to the lab.

## Steps

1. **Preflight.** `git log --oneline -1` shows ⟨sha⟩. Record `git status` (noise is expected).
2. **Build venv.** `.venv-build\Scripts\python -m pip install -r requirements.txt pyinstaller pytest pillow`. Confirm openpyxl is now installed.
3. **Unit tests on Windows.** `$env:PYTHONPATH = "src"`, then `.venv-build\Scripts\python -m pytest tests -q`. Expect ⟨N⟩ passed.
4. **Build** with `--distpath D:\projects\chipOid\dist --workpath D:\projects\chipOid\build` (see `docs/WINDOWS_SESSION.md`, step 4). Record the build time and `.exe` size, and any PyInstaller warnings that mention `chipoid`, `openpyxl` or `imagecodecs`.
5. **Generic smoke tests 1–9** from `docs/WINDOWS_DESKTOP_BUNDLE.md`. For tests 4–7 use the EXP24 run below.
6. **EXP24 run in the GUI** (this is also the cross-platform check):
   - Copy the four raw TIFFs into one folder, `C:\Users\<you>\chipoid_smoke\exp24_in\`. They live in the four `ChipOid_<cond>\` folders under the EXP24 path in `LOCAL_SETUP.md`: `EXP24_Media.tif`, `EXP24_Laser_media.tif`, `EXP24_NCs-laser.tif`, `EXP24-TX100.tif`.
   - GUI settings:
     - Input = that folder; Output = `C:\Users\<you>\chipoid_smoke\exp24_out\`.
     - Extract channels **on**: brightfield page 0, green 1, red 2.
     - radius_min 35, radius_max 50, max_rows 25, max_cols 4.
     - Everything else at its default (exclusion on, threshold 50 for all markers). No filename parsing.
   - Expected (from the coordinator's Linux run of the same commit):
     - ⟨table: per image wells / detected / filled / n_included⟩
     - TX100: 100 detected, 0 filled, ⟨n⟩ included.
   - Compare:
     ```powershell
     .venv-build\Scripts\python scripts\validate_exp.py `
       --run C:\Users\<you>\chipoid_smoke\exp24_out `
       --baseline D:\projects\chipOid\output\v010_validation\⟨rc_linux⟩
     ```
     Expect "source changed: none", max |dx|, |dy| = 0, and zero metric changes (float round-off at most). Paste the tables in the Report.
7. **Package.** Copy the `.exe` to `D:\projects\chipOid\dist\chipOid_v0.10.0.exe`. Copy ⟨release notes / user guide files⟩ next to it.

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
