"""chipoid.viz must force the non-interactive Agg backend.

Figures are only ever written to files, and in the GUI they are made on a
worker thread. Without an explicit backend, matplotlib picks TkAgg on Windows,
and Tk off the main thread is unsupported (it failed intermittently there).
"""
import matplotlib


def test_viz_forces_agg_backend():
    import chipoid.viz  # noqa: F401  (the import selects the backend)
    assert matplotlib.get_backend().lower() == "agg"
