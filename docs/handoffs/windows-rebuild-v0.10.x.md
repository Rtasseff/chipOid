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

<!-- Windows session: fill this in. -->

- Commit built:
- Unit tests (repo / test_viz):
- Integration tests ×2:
- Build: time, `.exe` size, SHA-256, new warnings:
- EXP24 check: counts, validation tables:
- P2 in Tk (each state; screenshots):
- Smoke test 2 + visual check (screenshots):
- Problems found (command, traceback, diagnosis, proposed fix):
- Packaged files (+ SHA-256):
