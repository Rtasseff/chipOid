# Building the chipOid Windows Desktop App

This document describes how to build `chipOid.exe`, the chipOid GUI, into a
single-file, self-contained Windows executable using PyInstaller. Modelled on
SegOid's `docs/WINDOWS_DESKTOP_BUNDLE.md`.

On this machine the build runs in a Windows Claude Code session on the WSL
folder, which reports back and never commits. See
[WINDOWS_SESSION.md](WINDOWS_SESSION.md) for that workflow; this file is the
build procedure itself.

## What you get

- A single `dist/chipOid.exe` (~200–250 MB) you can copy to any Windows 10/11
  machine and double-click. No Python install required on the target system.
- Bundles every chipOid runtime dependency (numpy, scipy, scikit-image,
  tifffile, imagecodecs, matplotlib, pandas, openpyxl, PIL, pyyaml) plus Tkinter.
- Bundles **no model**: chipOid is classical CV, nothing to ship beyond code.

## Prerequisites (on the build machine)

1. **Windows 10 or 11.** PyInstaller cross-compilation is unreliable;
   produce the Windows .exe on Windows. (WSL works too but the exe it
   produces is a Linux binary — not what we want.)
2. **Python 3.11 or newer.** Install from python.org (the embeddable build is
   fine). Confirm Tkinter is included: `python -c "import tkinter"` should
   succeed (it ships in the official Python installer by default).
3. **A clone of this repo.** Easiest: clone the repo onto the Windows
   filesystem directly. WSL paths (`\\wsl$\Ubuntu\...` or
   `\\wsl.localhost\Ubuntu\...`) work but have three well-known quirks:
   - PyInstaller's source-tree scan is noticeably slower over the share.
   - `pip install --upgrade pip` fails because pip can't replace its own
     executable on a network path; use `python -m pip install --upgrade pip`
     instead (or just skip the pip upgrade).
   - The project-root `dist/` and `build/` may be symlinks (to D drive).
     Windows over the 9p share can't reliably resolve Linux symlinks as
     directories, so PyInstaller's default `--distpath` / `--workpath`
     trip over `FileExistsError [WinError 183]`. Pass the flags explicitly
     pointing at native Windows paths (see Build steps below).
   If any of these bite, copy the repo to a native location (e.g.
   `C:\Users\<you>\chipOid`) and build from there with no extra flags.

## Build steps

```powershell
# 1) From a PowerShell window inside the repo:
cd <path-to>\chipOid

# 2) Install build-time dependencies into a fresh venv (recommended):
python -m venv .venv-build
.venv-build\Scripts\Activate.ps1
# Upgrading pip is optional. If you do upgrade, use the `python -m pip`
# form — bare `pip install --upgrade pip` fails on UNC paths
# (\\wsl.localhost\... or \\wsl$\...) because pip can't replace its own
# running executable. Just skip this line if 26.0.1+ is already installed.
python -m pip install --upgrade pip
# Runtime deps come from requirements.txt so new ones (e.g. openpyxl in v0.10)
# are picked up automatically. Re-run this before every build.
python -m pip install -r requirements.txt pyinstaller pillow

# 3) Build the .exe. --clean discards any stale PyInstaller caches.
#
# IMPORTANT when building from a WSL share path (\\wsl.localhost\... /
# \\wsl$\...): point --distpath and --workpath at native Windows paths.
# PyInstaller calls os.makedirs(..., exist_ok=True) and Windows over the
# 9p share can't reliably resolve a Linux symlink as a directory, so the
# default `dist\` and `build\` (which on this checkout are WSL symlinks)
# blow up with WinError 183 ("file already exists"). Writing to native
# Windows paths bypasses the symlink entirely — and the result lands in
# the same NTFS directory the WSL symlink points to.
python -m PyInstaller --clean --noconfirm `
  --distpath D:\projects\chipOid\dist `
  --workpath D:\projects\chipOid\build `
  chipoid_gui.spec

# If you cloned to a native Windows path (e.g. C:\Users\you\chipOid),
# you can skip the --distpath/--workpath flags entirely:
#   python -m PyInstaller --clean --noconfirm chipoid_gui.spec

# 4) Output:
#    D:\projects\chipOid\dist\chipOid.exe   <- the standalone executable
#    D:\projects\chipOid\build\             <- PyInstaller scratch; safe to delete
# From the WSL side, the same file is reachable as dist/chipOid.exe via
# the project-root symlink.
```

The build takes 2–4 minutes from a native Windows path, and about 10–12
minutes over the WSL share (11.4 min for v0.10.0). Final exe size is around
200 MB (matplotlib + scikit-image + scipy dominate).

## Smoke tests on the built .exe

After the build, run these checks before declaring victory:

1. **Launch from File Explorer.** Double-click `dist\chipOid.exe`. The window
   should appear within ~5 seconds, titled **"chipOid v<version>"** with the
   version from `src/chipoid/__init__.py`.
2. **Scroll through every section.** Confirm the form scrolls (mouse wheel
   and scroll bar both work) and that every section renders: Markers +
   Filename parsing, Extract channels, Detection, Lattice, Readout, Well
   inclusion, Output.
3. **Well inclusion defaults.** "Exclude empty wells" is on, "Same threshold
   for all markers" is on with 50, "exclude filled" is off, and "exclude
   clipped" is on. Untick "same for all" and confirm one threshold field
   appears per marker. Edit the markers field and confirm the per-marker
   fields follow.
4. **Run on a small test folder.** Copy 1–3 test images to a temp folder,
   pick it as Input, pick a fresh empty folder as Output, and click Run.
   Confirm the log streams in real time and that the output folder has
   `wells_all.csv`, `batch_summary.csv`, `wells_all.xlsx`, `run.log` and one
   `<image_id>/` subdirectory per image.
5. **Workbook.** Open `wells_all.xlsx` in Excel. It has the sheets
   `all_wells`, `included_wells`, `summary` and `settings`. `included_wells`
   has fewer rows than `all_wells` on images with empty wells, and `settings`
   shows the chipOid version. This proves openpyxl was bundled.
6. **Excluded wells in the figures.** In `review.png` and
   `04_intensity_<marker>.png`, excluded wells are grey. `07_scatter.png`
   shows dashed threshold lines.
7. **File open in Excel.** Leave `wells_all.xlsx` (and `wells_all.csv`) open
   in Excel and Run again into the same Output folder. The run finishes, the
   log shows `[WARN] could not write ... (is it open in Excel?)`, and the
   files that weren't open are rewritten.
8. **Filename parsing.** Enable "Parse filenames into metadata fields", type
   a label list (e.g. `cell, cond, date`), and Run. Confirm the resulting
   `wells_all.csv` has those columns populated.
9. **Bad input handling.** Point Input at an empty folder: a friendly error
   dialog appears before the job starts.

If any of these fail, see Troubleshooting below.

## Troubleshooting

### `ImportError: No module named imagecodecs._imagecodecs`

PyInstaller didn't capture the C extensions. The spec already calls
`collect_dynamic_libs('imagecodecs')`, but reinstall order can matter:

```powershell
pip uninstall -y imagecodecs
pip install imagecodecs
python -m PyInstaller --clean --noconfirm chipoid_gui.spec
```

### Window flashes and closes immediately

A hidden import is missing. Run the exe from a PowerShell window
(`.\dist\chipOid.exe`) so the Python traceback prints before the process
exits. Add the missing module to `hiddenimports` in `chipoid_gui.spec` and
rebuild.

### `matplotlib.RuntimeError: Could not determine backend`

The Agg backend wasn't bundled. Confirm `'matplotlib.backends.backend_agg'`
is in the `hiddenimports` list of `chipoid_gui.spec` (it is, by default).
If you customised the spec and lost it, add it back.

### "Output folder is read-only" or similar I/O error

If you pointed Output at a path under `\\wsl$\...`, WSL share permissions
can refuse writes from a native Windows process. Pick a normal Windows
folder (e.g. `C:\Users\<you>\chipoid_runs\test1`).

### `FileExistsError: [WinError 183] Cannot create a file when that file already exists: '\\\\wsl.localhost\\...\\dist'`

PyInstaller's `os.makedirs(..., exist_ok=True)` is choking because Windows
over the WSL 9p share returns False from `os.path.isdir()` on a Linux
symlink-to-directory. The fix is in the build steps above: pass
`--distpath D:\projects\chipOid\dist --workpath D:\projects\chipOid\build`
(or wherever your D-drive target lives) to bypass the symlink. The .exe
ends up in the same NTFS directory either way; you're just sidestepping
the symlink layer.

### Build itself fails with "Cannot find module 'X'"

Verify the missing module is installed in the build venv (`pip list | findstr X`)
before re-running PyInstaller.

## Known limitations

- **No Cancel button mid-run.** Closing the window kills the daemon thread,
  but there's no graceful in-job cancel. Not scheduled yet.
- **No application icon.** The exe uses Python's generic icon. To customise,
  drop a 256×256 `.ico` file at `assets/chipoid.ico` and rebuild — the spec
  picks it up automatically.
- **WSL build environment.** You can build on WSL, but the result is a Linux
  binary. Use a native Windows Python to produce the Windows `.exe`.

## Updating the build

Whenever you change Python code under `src/`, re-run the dependency install
(step 2) and rebuild with the same command as step 3:

```powershell
python -m pip install -r requirements.txt pyinstaller pillow
python -m PyInstaller --clean --noconfirm `
  --distpath D:\projects\chipOid\dist `
  --workpath D:\projects\chipOid\build `
  chipoid_gui.spec
```

`--clean` is important: PyInstaller caches dependency analysis aggressively
and stale caches are a common source of "I updated the source but the .exe
still does the old thing" surprises.
