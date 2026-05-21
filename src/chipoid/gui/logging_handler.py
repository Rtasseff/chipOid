"""Thread-safe log streaming from the worker thread to the GUI Text widget.

Pattern (same as SegOid):
  - The worker thread NEVER touches Tk widgets directly. It calls
    `GUILogHandler.push(msg)` which is just a queue.Queue.put.
  - The main thread polls the queue via `tk.Tk.after(...)` and drains lines
    into a ScrolledText widget.

This way Tk's "must only be accessed from the thread that created it" rule
is respected even though the pipeline runs in a worker thread.
"""
from __future__ import annotations

import queue
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from .widgets import ScrolledText


class GUILogHandler:
    """Bridge between worker-thread log calls and the main-thread Text widget."""

    POLL_INTERVAL_MS = 100

    def __init__(self, root: "tk.Misc", text_widget: "ScrolledText"):
        self._root = root
        self._text = text_widget
        self._queue: queue.Queue[str] = queue.Queue()
        self._running = False

    def push(self, msg: str) -> None:
        """Called from any thread. Appends a single message to the queue.

        We add a timestamp here (cheap, thread-safe) so the GUI log shows
        when each line was emitted by the pipeline.
        """
        ts = time.strftime("%H:%M:%S")
        self._queue.put(f"[{ts}] {msg}\n")

    def start(self) -> None:
        """Begin draining the queue. Call from the main thread once at startup."""
        if self._running:
            return
        self._running = True
        self._drain()

    def stop(self) -> None:
        self._running = False

    def _drain(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                self._text.append(msg)
        except queue.Empty:
            pass
        if self._running:
            self._root.after(self.POLL_INTERVAL_MS, self._drain)
