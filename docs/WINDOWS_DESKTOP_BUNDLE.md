# Building the chipOid Windows Desktop App

This document describes how to build `chipOid.exe` — the **Developer Version
v0.9** GUI — into a single-file, self-contained Windows executable using
PyInstaller. Modelled on SegOid's `docs/WINDOWS_DESKTOP_BUNDLE.md`.

## What you get

- A single `dist/chipOid.exe` (~200–250 MB) you can copy to any Windows 10/11
  machine and double-click. No Python install required on the target system.
- Bundles every chipOid runtime dependency (numpy, scipy, scikit-image,
  tifffile, imagecodecs, matplotlib, pandas, PIL, pyyaml) plus Tkinter.
- Bundles **no model**: chipOid is classical CV, nothing to ship beyond code.

## Prerequisites (on the build machine)

1. **Windows 10 or 11.** PyInstaller cross-compilation is unreliable;
   produce the Windows .exe on Windows. (WSL works too but the exe it
   produces is a Linux binary — not what we want.)
2. **Python 3.11 or newer.** Install from python.org (the embeddable build is
   fine). Confirm Tkinter is included: `python -c "import tkinter"` should
   succeed (it ships in the official Python installer by default).
3. **A clone of this repo.** Easiest: clone the repo onto the Windows
   filesystem directly. WSL paths (`\\wsl$\Ubuntu\...`) work but can be
   slow during the PyInstaller scan.

## Build steps

```powershell
# 1) From a PowerShell window inside the repo:
cd <path-to>\chipOid

# 2) Install build-time dependencies into a fresh venv (recommended):
python -m venv .venv-build
.venv-build\Scripts\Activate.ps1
pip install --upgrade pip
pip install numpy scipy scikit-image tifffile imagecodecs pandas matplotlib pillow pyyaml pyinstaller

# 3) Build the .exe. --clean discards any stale PyInstaller caches.
python -m PyInstaller --clean --noconfirm chipoid_gui.spec

# 4) Output:
#    dist\chipOid.exe   <- the standalone executable
#    build\             <- PyInstaller scratch; safe to delete
```

The build takes 2–4 minutes on a modern laptop. Final exe size is around
200 MB (matplotlib + scikit-image + scipy dominate).

## Smoke tests on the built .exe

After the build, run these checks before declaring victory:

1. **Launch from File Explorer.** Double-click `dist\chipOid.exe`. The window
   should appear within ~5 seconds with the title **"chipOid — Developer
   Version v0.9"**.
2. **Scroll through every section.** Confirm the form is scrollable
   (mouse-wheel and scroll-bar both work) and that all sections render —
   Markers + Filename parsing, Extract channels, Detection, Lattice,
   Readout, Output figures.
3. **Run on a small test folder.** Copy 2–3 brightfield TIFFs (with
   companions) to a temp folder, pick that as Input, pick a fresh empty
   folder as Output, click Run. Confirm the log streams in real time and
   that `wells_all.csv`, `batch_summary.csv`, and per-image `<image_id>/`
   subdirectories appear in the output folder.
4. **Filename parsing.** Enable "Parse filenames into metadata fields", type
   a label list (e.g. `cell, cond, date`), Run. Confirm the resulting
   `wells_all.csv` has those columns populated.
5. **Bad input handling.** Point Input at an empty folder → friendly error
   dialog before the job starts.

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

### Build itself fails with "Cannot find module 'X'"

Verify the missing module is installed in the build venv (`pip list | findstr X`)
before re-running PyInstaller.

## Known limitations (v0.9)

- **No Cancel button mid-run.** Closing the window kills the daemon thread,
  but there's no graceful in-job cancel. Planned for v0.10.
- **No application icon.** The exe uses Python's generic icon. To customise,
  drop a 256×256 `.ico` file at `assets/chipoid.ico` and rebuild — the spec
  picks it up automatically.
- **WSL build environment.** You can build on WSL, but the result is a Linux
  binary. Use a native Windows Python to produce the Windows `.exe`.

## Updating the build

Whenever you change Python code under `src/`, rebuild with the same command:

```powershell
python -m PyInstaller --clean --noconfirm chipoid_gui.spec
```

`--clean` is important: PyInstaller caches dependency analysis aggressively
and stale caches are a common source of "I updated the source but the .exe
still does the old thing" surprises.
