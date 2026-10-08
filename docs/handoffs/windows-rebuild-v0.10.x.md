> **Done 2026-10-08.** Passed; `v0.10.0` is tagged on the build commit `c902446`. Kept as a record.

# Handoff — Windows rebuild of chipOid v0.10.0 (P1/P2 fixes)

| | |
|---|---|
| Session | Windows Claude Code session on the main checkout via the WSL share |
| Build commit | `main` at or after `a2411b3` (version stays `0.10.0`; see step 1) |
| Base | the first build, report in `docs/handoffs/windows-build-v0.10.md` |
| Created | 2026-10-08 |
| Issues | #17 (Agg backend) · #18 (greyed-out per-marker fields) · #5 |
| Coordinator session | WSL, `~/projects/miniProjects/202605_chipOid/` |

Read `docs/WINDOWS_SESSION.md` first: it has the rules (git read-only, no
edits to tracked files, report here) and the standard procedure. Concrete
paths are in `LOCAL_SETUP.md`. As last time, running git read-only through
`wsl.exe git ...` avoids the Git-for-Windows noise.

## Goal

The first v0.10.0 build passed, but nothing has gone to the lab yet. Two
problems from its report were fixed in `a2411b3`:

- **P1 (#17):** `chipoid.viz` now forces the Agg backend. Before, matplotlib picked TkAgg on Windows and made figures through Tk on the GUI's worker thread, which caused the intermittent `TclError` in `test_pipeline_in_memory.py`.
- **P2 (#18):** per-marker threshold fields added while "Exclude empty wells" is off are now greyed out like the rest of the section. This has only been compile-checked; WSL has no Tk.

Rebuild the `.exe` from that commit, prove both fixes on Windows, finish the
two checks that needed an unlocked PC, and re-package for delivery. The
version number stays **0.10.0**: no tag or release was ever published.

## Scope

**In:** rebuild, re-run the tests, the EXP24 cross-platform check, P2 in the
Tk GUI, smoke test 2, a visual check of two sections, re-packaging.

**Out:** code edits of any kind (report problems with a proposed fix, as
before). Any git write command.

## Acceptance

1. **Preflight.**
   - `wsl.exe git -C <repo> log --oneline -3`: HEAD is `a2411b3` or a later docs-only commit.
   - `wsl.exe git -C <repo> diff --stat a2411b3 HEAD -- src chipoid_gui.spec requirements.txt pyproject.toml` prints nothing.
   - `src/chipoid/viz.py` contains `matplotlib.use("Agg")` before the pyplot import.
2. **Build venv.** Re-run `.venv-build\Scripts\python -m pip install -r requirements.txt pyinstaller pytest pillow`. Nothing new is expected; record if anything changes.
3. **Unit tests.**
   - From the repo, with `$env:PYTHONPATH = "src"`: `.venv-build\Scripts\python -m pytest tests -q`. Expect **106 passed, 8 skipped** (114 tests; the 8 skips are `test_pipeline_in_memory.py`, because of the `data\` symlink).
   - Also confirm `tests\test_viz.py` passes on Windows. That's where it matters: `get_backend()` must be `agg`.
4. **Integration tests on Windows (P1).**
   - Work from a scratch folder where `data` is a junction to `D:\projects\chipOid\data` (`C:\Users\<you>\chipoid_smoke\pytest_cwd`, from last time). If the junction is gone: `cmd /c mklink /J data D:\projects\chipOid\data`.
   - Run there: `$env:PYTHONPATH="<repo>\src"; .venv-build\Scripts\python -m pytest <repo>\tests\test_pipeline_in_memory.py -q`.
   - Expect **8 passed**. Run the full file **twice**: the old failure showed up in 2 of 2 full-file runs.
5. **Rebuild** with `--distpath D:\projects\chipOid\dist --workpath D:\projects\chipOid\build` (about 11 min over the share). Record the time, size, SHA-256, and any new warnings compared with the first build.
6. **EXP24 cross-platform check.** Repeat step 6 of `windows-build-v0.10.md` with the new `.exe`.
   - Same input folder (`C:\Users\<you>\chipoid_smoke\exp24_in`) and the same GUI settings.
   - Output to a fresh folder, `C:\Users\<you>\chipoid_smoke\exp24_out_rebuild`.
   - Run `scripts\validate_exp.py --run <that folder> --baseline D:\projects\chipOid\output\v010_validation\rc_linux`.
   - Expect **zero differences**: source changed none, max |dx|, |dy| = 0, 0 wells with metric changes, and included 91 / 96 / 95 / 20. The only expected column difference is `condition` in the baseline.
   - No `[WARN]` lines in `run.log`.
7. **P2 in the Tk GUI** (the PC will be unlocked; use the real mouse).
   1. Untick "Exclude empty wells", untick "Same threshold for all markers", then append `, blue` to the markers field. **All three** per-marker fields, including the new `blue` one, are greyed out.
   2. Tick "Exclude empty wells" again: all fields are enabled. Untick it: all are greyed out.
   3. Put the markers back to `green, red` before closing.
   4. Screenshot each state.
8. **Smoke test 2 + visual check.** Do test 2 from `docs/WINDOWS_DESKTOP_BUNDLE.md` with the real mouse.
   - The mouse wheel and the scroll bar both scroll the form.
   - Scroll down and look at the **"Well inclusion (exclude empty wells)"** and **"Output"** sections. They render without clipped or overlapping labels, the notes are readable, and the defaults match test 3.
   - Screenshot both sections.
9. **Re-package.**
   - Replace `D:\projects\chipOid\dist\chipOid_v0.10.0.exe` with the new build. Delete or overwrite the old one so nothing stale can be handed over.
   - Copy the current `docs\RELEASE_NOTES_v0.10.md` and `docs\LIVE_DEAD_GUIDE.md` next to it. The guide has one new sentence.
   - Record the SHA-256 of the packaged `.exe`.

## Status

- [ ] 1–3 preflight, venv, unit tests
- [ ] 4 integration tests ×2
- [ ] 5 rebuild
- [ ] 6 EXP24 check
- [ ] 7 P2 in Tk
- [ ] 8 smoke test 2 + visual check
- [ ] 9 re-package

## Questions for the coordinator

-

## Return protocol

1. Fill in the **Report** below. Keep LF line endings if your editor allows, and write `C:\Users\<you>\...` rather than the real user name in paths.
2. Tell the human you're done. The coordinator reads the report, then tags `v0.10.0` on the build commit, closes #5, and the human hands the `.exe` to the lab.

## Report

Windows session, 2026-10-08. **Verdict: ready to tag and hand over.**
- All nine acceptance steps pass.
- P1 and P2 are confirmed fixed on Windows.
- The rebuilt `.exe` gives exactly the same EXP24 numbers as Linux.
- No new problems.

Screenshots are in `C:\Users\<you>\chipoid_smoke\shots\` (file names below).

### Commit built
- `c902446` on `main`, a docs-only commit after `a2411b3`.
- `git diff --stat a2411b3 HEAD -- src chipoid_gui.spec requirements.txt pyproject.toml` prints nothing.
- `git status` is clean. Git was run read-only through `wsl.exe`.
- `src/chipoid/viz.py` has `matplotlib.use("Agg")` on line 17, before the pyplot import on line 20.
- `__version__ = "0.10.0"`.

### Build venv
`pip install -r requirements.txt pyinstaller pytest pillow` changed nothing. Same versions as the first build: Python 3.13.14, PyInstaller 6.20.0, numpy 2.4.6, pandas 3.0.3, scikit-image 0.26.0, scipy 1.17.1, matplotlib 3.10.9, tifffile 2026.5.15, imagecodecs 2026.5.10, openpyxl 3.1.5.

### Unit tests
- **Repo:** `pytest tests -q` gives **106 passed, 8 skipped**. The skips are `test_pipeline_in_memory.py`, because of the `data\` symlink.
- **test_viz:** `tests\test_viz.py::test_viz_forces_agg_backend` **PASSED** on Windows.

### Integration tests ×2 (P1)
- Run from `C:\Users\<you>\chipoid_smoke\pytest_cwd`, with `data` a junction to `D:\projects\chipOid\data`: `pytest <repo>\tests\test_pipeline_in_memory.py -q -rs -l`.
- **Run 1: 8 passed (177 s). Run 2: 8 passed (179 s).**
- The `TclError` failure from the first build (2 of 2 runs) is gone. **P1 is fixed.**

### Build
- **Time:** 603 s.
- **`chipOid.exe`:** 148,359,054 bytes. SHA-256 `0ed5e766d09d676bb3d95092f21f3f2b0066aec250aca630453cc41019dca9e9`.
- **Warnings:** the same 9 as the first build (order only differs); none new.
- The build log says `Selected matplotlib backends: ['Agg', 'TkAgg']`. The bundle still contains TkAgg, but the code now forces Agg at runtime. A possible size trim is in the notes.

### EXP24 check
- Brief settings, in the new `.exe`. Driven by keyboard messages; all settings confirmed in `run.log`'s effective config.
- Output: `C:\Users\<you>\chipoid_smoke\exp24_out_rebuild`.
- The run took about 45 s. Status: `Done. 4/4 images succeeded`.
- **No `[WARN]` or `[ERROR]` lines** in `run.log`.

| image | wells | detected | filled | included | lattice QC residual median / p95 (px) |
|---|---|---|---|---|---|
| EXP24_Media | 100 | 100 | 0 | 91 | 3.1 / 6.3 |
| EXP24_Laser_media | 100 | 100 | 0 | 96 | 2.5 / 5.0 |
| EXP24_NCs-laser | 100 | 100 | 0 | 95 | 3.1 / 5.2 |
| EXP24-TX100 | 100 | 100 | 0 | 20 | 3.2 / 6.1 |

`validate_exp.py --run …\exp24_out_rebuild --baseline D:\projects\chipOid\output\v010_validation\rc_linux`:

Columns only in run: none · only in baseline: ['condition'] (expected)

| image | wells (run/base) | source changed | max abs dx, dy (px) | wells with any metric change | max abs d signal_* |
|---|---|---|---|---|---|
| EXP24-TX100 | 100/100 | none | 0, 0 | 0 | 0 |
| EXP24_Laser_media | 100/100 | none | 0, 0 | 0 | 0 |
| EXP24_Media | 100/100 | none | 0, 0 | 0 | 0 |
| EXP24_NCs-laser | 100/100 | none | 0, 0 | 0 | 0 |

Workbook: sheets `all_wells` (400 rows), `included_wells` (302), `summary` (4) and `settings` (`chipoid_version = 0.10.0`). The green-fraction table is identical to the first build's report: TX100 included = 20 / 2.6 % / pooled 2.1 %.

### P2 in Tk (real mouse, in the `.exe`): PASS
Order note: "Same threshold for all markers" has to be unticked **before** "Exclude empty wells". Once exclusion is off, the whole sub-section is disabled, including "Same". So the run was:

| State | Result | Screenshot |
|---|---|---|
| (a) "Same" unticked | green and red per-marker fields shown, enabled | `p2_a_same_off.png` |
| (b) "Exclude empty wells" unticked | green and red fields, "Same", exclude-filled and exclude-clipped all greyed out | `p2_r1_excl_off.png` |
| (c) `, blue` appended to markers | `green, red, blue` | `p2_r3_markers.png` |
| (d) after (c), exclusion still off | **three** fields: green, red and the new **blue**, all greyed out | `p2_r4_blue_excl_off.png` |
| (e) "Exclude empty wells" ticked | all three fields enabled | `p2_f_excl_on.png` |
| (f) unticked again | all three greyed out | `p2_g_excl_off_again.png` |
| (g) restored | exclusion on, "Same" on (50), markers back to `green, red` | `p2_h_defaults.png`, `p2_i_markers_restored.png` |

The in-process check from the same source (`gui_test3.py`) is now 26/26. In the first build the "new field greyed out" check was the only failure.

### Smoke test 2 + visual check: PASS
- **Scroll bar:** PASS. Clicking the trough pages up and down (`m2_scrollbar_click.png`), and dragging the thumb scrolls (`m2_scrollbar_drag2.png`).
- **Mouse wheel:** PASS; the direction follows Windows.
  - The wheel scrolls the form. On this PC rolling toward the user scrolls **up**, because the user has reversed ("natural") scrolling set system-wide. The human confirmed this by hand on the `.exe` and said it's how they like it.
  - Injected wheel events (pyautogui and raw `SendInput`) are flipped the same way on this machine. An instrumented in-process run showed Tk receiving delta = +120 for an injected −120.
  - The handler is the standard Tk formula (`yview_scroll(-delta/40)`), so on a PC with default settings rolling toward the user scrolls down.
- **Test-method note:** the Claude terminal window overlapped the left part of the chipOid window and kept taking wheel events. The tests were redone with chipOid at (1100, 0), clear of the terminal.
- **Visual check:** PASS. **"Well inclusion (exclude empty wells)"** and **"Output"** render cleanly in the `.exe`: no clipped or overlapping labels, notes readable, defaults match test 3 (exclusion on, "Same" on with 50, exclude-filled off, exclude-clipped on, workbook on). Screenshot: `p2_02.png`.

### Problems found
None blocking. One optional note:
- **Size trim (optional, not needed for this release).** PyInstaller still bundles `matplotlib.backends.backend_tkagg` (`Selected matplotlib backends: ['Agg', 'TkAgg']`). Since Agg is forced, adding `hooksconfig={"matplotlib": {"backends": "Agg"}}` to `chipoid_gui.spec` would leave TkAgg out and shave a little off the `.exe`. Tk itself stays, because the GUI needs it.

### Packaged files
In `D:\projects\chipOid\dist\`:
- **`chipOid_v0.10.0.exe`:** 148,359,054 bytes, SHA-256 `0ed5e766d09d676bb3d95092f21f3f2b0066aec250aca630453cc41019dca9e9`. It overwrote the first build, which had a different hash, so nothing stale is left. Identical to `chipOid.exe`.
- **`RELEASE_NOTES_v0.10.md`:** copied from `docs\` at `c902446`.
- **`LIVE_DEAD_GUIDE.md`:** copied from `docs\` at `c902446`, including the new sentence about retyping markers. Verified identical to the repo copy.
