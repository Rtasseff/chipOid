"""Entry so `python -m chipoid.gui` launches the app.

Uses an ABSOLUTE import, not a relative one. This file is the entry point
PyInstaller bundles, and PyInstaller runs it as a top-level script with no
`__package__` — a relative import (`from .app import ...`) fails with
"attempted relative import with no known parent package" in that context.
Absolute import works in both modes:
  - `python -m chipoid.gui`     — Python resolves chipoid.gui.app via sys.path
  - PyInstaller-frozen exe      — chipoid package is bundled and on sys.path
"""
from chipoid.gui.app import main

if __name__ == "__main__":
    main()
