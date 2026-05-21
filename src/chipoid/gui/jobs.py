"""Background pipeline execution for the chipOid GUI.

Wraps `chipoid.pipeline.run_batch_in_memory` in a daemon thread so the GUI
doesn't freeze while the pipeline runs. Log lines go through the supplied
callback (typically `GUILogHandler.push`) which is queue-backed and
thread-safe; the on_complete callback also returns via the queue path
(re-scheduled onto the main thread via `root.after(0, ...)` by the caller).
"""
from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

import pandas as pd


class PipelineJob:
    """One-shot batch run. Construct, then call .start()."""

    def __init__(
        self,
        cfg: dict,
        manifest: pd.DataFrame,
        log_callback: Callable[[str], None],
        on_complete: Callable[[bool, str, dict | None], None],
    ):
        self.cfg = cfg
        self.manifest = manifest
        self.log_callback = log_callback
        self.on_complete = on_complete
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("job already running")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        try:
            # Imported lazily so the GUI module can be imported in environments
            # without all the pipeline deps (e.g. early test scaffolding).
            from chipoid.pipeline import run_batch_in_memory
            result = run_batch_in_memory(
                self.cfg, self.manifest, log=self.log_callback,
                config_label="GUI",
            )
            ok = result.get("n_failed", 0) == 0
            msg = (f"{result.get('n_success', 0)}/{result.get('n_images', 0)} "
                   f"images succeeded; output in {result.get('out_root')}")
            self.on_complete(ok, msg, result)
        except Exception as e:
            tb = traceback.format_exc()
            self.log_callback(f"[ERROR] {e!r}")
            self.log_callback(tb)
            self.on_complete(False, f"Error: {e}", None)
