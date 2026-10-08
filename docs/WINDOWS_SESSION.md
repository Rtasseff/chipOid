# The Windows session

chipOid is developed in WSL (Ubuntu). A few things have to happen on native
Windows: building `chipOid.exe` with PyInstaller, smoke-testing the `.exe`,
and reproducing Windows-only bugs. Those run in a **Windows Claude Code
session** opened on the same folder through the WSL share. Everything else
(code, commits, merges, releases) happens in WSL.

The Windows session **reports back; it never commits.** Two git programs on
one working tree cause index locks and file-mode noise, and Windows editors
can introduce CRLF line endings. So the Windows session builds and tests, and
writes what it found into its brief. The coordinator session in WSL makes any
code fix, and the Windows session rebuilds.

## Layout

| What | WSL path | Windows path |
|---|---|---|
| Repo (main checkout) | `~/projects/miniProjects/202605_chipOid` | `\\wsl.localhost\Ubuntu\home\<user>\projects\miniProjects\202605_chipOid` |
| Build venv (gitignored) | `.venv-build/` | `.venv-build\` (Windows Python 3.11+; currently 3.13) |
| Built `.exe` | `dist/` (symlink to D drive) | `D:\projects\chipOid\dist\` |
| PyInstaller scratch | `build/` (symlink to D drive) | `D:\projects\chipOid\build\` |

Concrete paths for this machine (user name, the Windows Python used to create
`.venv-build`, the test-data location) are in `LOCAL_SETUP.md` (gitignored).

`dist\` and `build\` are Linux symlinks. Windows can't treat them as
directories over the share, so **always** pass `--distpath` and `--workpath`
with the `D:\` paths (see `docs/WINDOWS_DESKTOP_BUNDLE.md`).

## Starting it (human)

1. Make sure the coordinator has merged everything for the build and that the
   main checkout is on `main`. Never point the Windows session at a worktree
   under `202605_chipOid-wt\`.
2. Open PowerShell and run:
   ```powershell
   cd \\wsl.localhost\Ubuntu\home\<user>\projects\miniProjects\202605_chipOid
   claude
   ```
   (or open that folder in the Claude desktop app).
3. Paste:
   > You are the Windows session for chipOid. Read `docs/WINDOWS_SESSION.md`, then `docs/handoffs/windows-build-<version>.md`, and carry out that brief. Report in the brief's Report section. Do not run git commands that change anything, and do not edit tracked source files.
4. When it's done, tell the coordinator. The coordinator reads the report, fixes anything that needs fixing, and commits the report.

Claude Code memory is per directory, and the Windows path differs from the WSL
one, so the Windows session starts with no memory. This file and the brief
are its context.

## Rules for the Windows session (agent)

- **Git is read-only.** `git log` and `git status` are fine. Never commit, push, checkout, stash, reset, rebase or `git add`. Git for Windows on a WSL repo may report every file as modified (file mode or line-ending noise); ignore it and don't "fix" it.
- **May write:**
  - the **Report** section of its brief (keep LF line endings if your editor allows);
  - PyInstaller output under `D:\projects\chipOid\{dist,build}\`;
  - scratch test folders on the Windows side (e.g. `C:\Users\<you>\chipoid_smoke\`);
  - packages into `.venv-build\` (untracked).
- **Must not edit:** tracked source, config, spec or docs files. If something fails, write down the exact command, the full traceback, your diagnosis and a proposed fix (a diff is ideal) in the Report, and stop that line of work. The coordinator applies the fix in WSL; then you rebuild.
- **Data:** read lab data from its OneDrive location (path in `LOCAL_SETUP.md`) and write outputs only to scratch folders. Never copy lab data into the repo.

## Standard build-and-test procedure

The brief for each build says which commit, which checks, and the expected
numbers. The usual steps:

1. **Preflight.** `git log --oneline -1` shows the commit named in the brief. Note `git status` (expect noise, not real changes).
2. **Update the build venv:**
   ```powershell
   .venv-build\Scripts\python -m pip install -r requirements.txt pyinstaller pytest
   ```
3. **Unit tests on Windows** (catch path and encoding bugs before building):
   ```powershell
   $env:PYTHONPATH = "src"
   .venv-build\Scripts\python -m pytest tests -q
   ```
4. **Build** (~11 min over the WSL share):
   ```powershell
   .venv-build\Scripts\python -m PyInstaller --clean --noconfirm `
     --distpath D:\projects\chipOid\dist `
     --workpath D:\projects\chipOid\build `
     chipoid_gui.spec
   ```
5. **Smoke tests** from `docs/WINDOWS_DESKTOP_BUNDLE.md`, plus anything the brief adds.
6. **Cross-platform check.** Run the `.exe` on the brief's test images with the brief's settings, then compare against the coordinator's Linux run of the same commit:
   ```powershell
   .venv-build\Scripts\python scripts\validate_exp.py --run <windows output> --baseline <linux output>
   ```
   Expect zero differences, or float round-off only.
7. **Package** for handover: copy `D:\projects\chipOid\dist\chipOid.exe` to `D:\projects\chipOid\dist\chipOid_v<version>.exe`, plus any files the brief lists (release notes, user guide).
8. **Report** in the brief:
   - commit built, Python and PyInstaller versions, `.exe` size;
   - the test-suite result;
   - a pass/fail checklist for every smoke test;
   - the validation tables;
   - problems found with proposed fixes;
   - the path of the packaged `.exe`.

Then tell the human you're done.
