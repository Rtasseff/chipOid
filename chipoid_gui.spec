# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for chipOid Developer Version v0.9 GUI.
# Build (from a Windows shell with Python + PyInstaller installed):
#     python -m PyInstaller --clean --noconfirm chipoid_gui.spec
#
# Patterned after SegOid's segoid_gui.spec, stripped of ONNX / model bundling
# (chipOid is classical CV — no ML model to ship) and tightened to chipOid's
# deps. See docs/WINDOWS_DESKTOP_BUNDLE.md for the full build procedure.

from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

block_cipher = None

# --- Heavyweight scientific-Python packages -------------------------------- #
# Each collect_all() returns (datas, binaries, hiddenimports). We unpack and
# concatenate so PyInstaller picks up the .so/.dll/.pyd extensions and any
# resource files (CRT redistributables, .pyi stubs, etc.).
pandas_d,      pandas_b,      pandas_h      = collect_all('pandas')
scipy_d,       scipy_b,       scipy_h       = collect_all('scipy')
skimage_d,     skimage_b,     skimage_h     = collect_all('skimage')
imagecodecs_d, imagecodecs_b, imagecodecs_h = collect_all('imagecodecs')
imagecodecs_dyn = collect_dynamic_libs('imagecodecs')
tifffile_d,    tifffile_b,    tifffile_h    = collect_all('tifffile')
matplotlib_d,  matplotlib_b,  matplotlib_h  = collect_all('matplotlib')
pil_d,         pil_b,         pil_h         = collect_all('PIL')
yaml_d,        yaml_b,        yaml_h        = collect_all('yaml')

project_root = Path(SPECPATH)

datas = []
icon_file = project_root / 'assets' / 'chipoid.ico'
if icon_file.exists():
    datas.append((str(icon_file), 'assets'))

a = Analysis(
    [str(project_root / 'src' / 'chipoid' / 'gui' / '__main__.py')],
    pathex=[str(project_root / 'src')],
    binaries=(
        pandas_b + scipy_b + skimage_b
        + imagecodecs_b + imagecodecs_dyn
        + tifffile_b + matplotlib_b + pil_b + yaml_b
    ),
    datas=(
        datas + pandas_d + scipy_d + skimage_d
        + imagecodecs_d + tifffile_d + matplotlib_d + pil_d + yaml_d
    ),
    hiddenimports=[
        # PIL (used transitively by matplotlib for raster writes).
        'PIL', 'PIL.Image', 'PIL.TiffImagePlugin',
        # tifffile reads our microscopy TIFFs.
        'tifffile', 'tifffile.tifffile',
        # imagecodecs ships C extensions that PyInstaller often misses.
        'imagecodecs', 'imagecodecs._imagecodecs',
        # scikit-image submodules used by chipoid.detect / chipoid.lattice.
        'skimage', 'skimage.feature', 'skimage.transform',
        'skimage.draw', 'skimage.measure', 'skimage.filters', 'skimage.util',
        # scipy submodules used by chipoid.lattice (cKDTree) and friends.
        'scipy', 'scipy.ndimage', 'scipy.spatial',
        # matplotlib + the Agg backend (we never use an interactive backend).
        'matplotlib', 'matplotlib.backends.backend_agg',
        # numpy & pandas internals that one_file builds sometimes miss.
        'numpy', 'numpy.core._methods',
        'pandas', 'pandas._libs', 'pandas._libs.tslibs',
        # yaml: pure python but pyinstaller occasionally misses the loader.
        'yaml',
        # Tkinter — stdlib, but PyInstaller likes explicit hints.
        'tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox',
        # chipOid package + every submodule. Listing them avoids surprises.
        'chipoid', 'chipoid.cli', 'chipoid.config', 'chipoid.detect',
        'chipoid.extract', 'chipoid.lattice', 'chipoid.manifest',
        'chipoid.pipeline', 'chipoid.readout', 'chipoid.viz',
        'chipoid.gui', 'chipoid.gui.app', 'chipoid.gui.widgets',
        'chipoid.gui.config_form', 'chipoid.gui.config_form_logic',
        'chipoid.gui.manifest_builder', 'chipoid.gui.filename_schema',
        'chipoid.gui.jobs', 'chipoid.gui.logging_handler',
    ] + pandas_h + scipy_h + skimage_h + imagecodecs_h
      + tifffile_h + matplotlib_h + pil_h + yaml_h,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # chipOid is classical CV; reject anything that would bloat the binary.
        'torch', 'torchvision', 'tensorflow', 'keras', 'tensorboard',
        'onnxruntime', 'onnx',
        'cv2', 'opencv-python',
        'pytest', 'black', 'flake8',
        'IPython', 'jupyter', 'notebook',
        'sphinx', 'docutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='chipOid.exe' if sys.platform == 'win32' else 'chipOid',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
)
