"""chipOid main GUI window — Developer Version v0.9.

Architecture mirrors SegOid's `src/gui/app.py`:
  - tk.Tk root with a top title, scrollable Canvas+Frame for the config form,
    a control bar (Input/Output folder pickers + Run button), and a log Text
    widget at the bottom.
  - Background work runs in a worker thread via `jobs.PipelineJob`; log lines
    flow through `logging_handler.GUILogHandler` (queue + after-poll) so Tk
    is only ever touched on the main thread.

v0.9 calls out the developer status prominently in the window title and a
header label.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.messagebox
from copy import deepcopy
from pathlib import Path
from tkinter import ttk

from chipoid.config import DEFAULTS, _deep_merge
from chipoid.manifest import validate_manifest

from .config_form import ConfigForm
from .filename_schema import create_schema_from_labels
from .jobs import PipelineJob
from .logging_handler import GUILogHandler
from .manifest_builder import scan_folder_for_images
from .widgets import FolderPicker, ScrolledText


APP_TITLE = "chipOid — Developer Version v0.9"


class ChipOidApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("960x900")
        self.root.minsize(800, 600)

        # --- Top container -------------------------------------------- #
        main = ttk.Frame(root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        # Title banner identifying the developer build.
        title = ttk.Label(
            main, text=APP_TITLE,
            font=("TkDefaultFont", 13, "bold"),
            foreground="#883300",
        )
        title.pack(pady=(0, 2))
        subtitle = ttk.Label(
            main,
            text="Developer build: every pipeline option is surfaced below with a short note. "
                 "Pick an input folder + output folder, adjust knobs, click Run.",
            foreground="#666666", wraplength=900, justify=tk.CENTER,
        )
        subtitle.pack(pady=(0, 8))

        # --- Folder pickers (always visible above the scrollable area) - #
        io_frame = ttk.LabelFrame(main, text="Input / Output", padding=8)
        io_frame.pack(fill=tk.X, pady=4)
        self.input_picker = FolderPicker(io_frame, label="Input folder:")
        self.input_picker.pack(fill=tk.X, pady=2)
        self.output_picker = FolderPicker(io_frame, label="Output folder:")
        self.output_picker.pack(fill=tk.X, pady=2)
        io_note = ttk.Label(
            io_frame,
            text="Input folder: contains <base>.tif brightfields and optional <base>_<marker>.tif "
                 "companions. Output folder: where chipOid writes per-image overlays and the "
                 "wells_all.csv batch table. The input folder is treated as read-only.",
            foreground="#666666", wraplength=900, justify=tk.LEFT,
            font=("TkDefaultFont", 8),
        )
        io_note.pack(fill=tk.X, anchor=tk.W, padx=4, pady=(2, 0))

        # --- Scrollable middle area for the config form --------------- #
        scroll_outer = ttk.Frame(main)
        scroll_outer.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(4, 4))

        self._scroll_canvas = tk.Canvas(scroll_outer, highlightthickness=0)
        scroll_bar = ttk.Scrollbar(scroll_outer, orient=tk.VERTICAL,
                                   command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=scroll_bar.set)
        scroll_bar.pack(side=tk.RIGHT, fill=tk.Y)
        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll_inner = ttk.Frame(self._scroll_canvas)
        self._scroll_inner_id = self._scroll_canvas.create_window(
            (0, 0), window=scroll_inner, anchor="nw"
        )
        scroll_inner.bind(
            "<Configure>",
            lambda _e: self._scroll_canvas.configure(
                scrollregion=self._scroll_canvas.bbox("all")
            ),
        )
        self._scroll_canvas.bind(
            "<Configure>",
            lambda e: self._scroll_canvas.itemconfig(self._scroll_inner_id, width=e.width),
        )
        # Mouse wheel binds only while cursor is inside the canvas (so the log
        # below remains independently scrollable).
        self._scroll_canvas.bind("<Enter>", self._bind_wheel)
        self._scroll_canvas.bind("<Leave>", self._unbind_wheel)

        # Build the config form inside the scrollable inner frame.
        self.form = ConfigForm(scroll_inner)

        # --- Control bar (Run button + status) ------------------------ #
        ctrl = ttk.Frame(main)
        ctrl.pack(fill=tk.X, pady=(6, 4))
        self.run_btn = ttk.Button(ctrl, text="Run", command=self._on_run)
        self.run_btn.pack(side=tk.LEFT, padx=4)
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(ctrl, textvariable=self.status, foreground="#444444").pack(side=tk.LEFT, padx=8)

        # --- Log area ------------------------------------------------- #
        log_frame = ttk.LabelFrame(main, text="Log", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=False, pady=(2, 0))
        self.log_widget = ScrolledText(log_frame, height=12, width=120)
        self.log_widget.pack(fill=tk.BOTH, expand=True)

        # Logging plumbing (queue-based, thread-safe).
        self.log_handler = GUILogHandler(self.root, self.log_widget)
        self.log_handler.start()

        self._job: PipelineJob | None = None

    # ------------------------------------------------------------------ #
    # Mouse-wheel scrolling
    # ------------------------------------------------------------------ #
    def _bind_wheel(self, _event):
        # Windows / macOS use <MouseWheel>; Linux uses Button-4 / Button-5.
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._scroll_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._scroll_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_wheel(self, _event):
        self._scroll_canvas.unbind_all("<MouseWheel>")
        self._scroll_canvas.unbind_all("<Button-4>")
        self._scroll_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._scroll_canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self._scroll_canvas.yview_scroll(3, "units")
        else:  # Windows: event.delta in multiples of 120
            self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 40)), "units")

    # ------------------------------------------------------------------ #
    # Run button
    # ------------------------------------------------------------------ #
    def _on_run(self):
        if self._job is not None and self._job.is_running():
            tk.messagebox.showinfo("chipOid", "A run is already in progress.")
            return

        input_dir = self.input_picker.get()
        output_dir = self.output_picker.get()
        if not input_dir or not Path(input_dir).is_dir():
            tk.messagebox.showerror("chipOid", "Pick a valid input folder first.")
            return
        if not output_dir:
            tk.messagebox.showerror("chipOid", "Pick an output folder first.")
            return

        # Build the config overrides from the form, then deep-merge onto defaults.
        try:
            overrides = self.form.to_cfg_overrides()
        except Exception as e:
            tk.messagebox.showerror("chipOid", f"Config error: {e}")
            return
        cfg = _deep_merge(deepcopy(DEFAULTS), overrides)
        # Wire the in-memory paths the form doesn't surface.
        cfg["input"]["data_root"] = input_dir
        cfg["output"]["dir"] = output_dir

        # Build the manifest from the input folder.
        try:
            schema = None
            if self.form.parse_filenames_enabled():
                labels = [t.strip() for t in self.form.filename_label_text().split(",") if t.strip()]
                schema = create_schema_from_labels(labels)
            manifest = scan_folder_for_images(
                Path(input_dir),
                markers=cfg["markers"],
                filename_schema=schema,
                data_root=Path(input_dir),
            )
        except Exception as e:
            tk.messagebox.showerror("chipOid", f"Manifest error: {e}")
            return

        if manifest.empty:
            tk.messagebox.showerror(
                "chipOid",
                f"No brightfield TIFFs found in {input_dir}.\n\n"
                f"Expected <base>.tif files (with optional <base>_<marker>.tif companions)."
            )
            return

        # Validate manifest shape (catches things like duplicate image_id).
        try:
            manifest = validate_manifest(manifest, where="GUI-built manifest")
        except Exception as e:
            tk.messagebox.showerror("chipOid", f"Manifest invalid: {e}")
            return

        self.log_widget.clear()
        self.log_handler.push(f"Starting run on {len(manifest)} images.")
        self.run_btn.config(state=tk.DISABLED)
        self.status.set(f"Running on {len(manifest)} images...")

        self._job = PipelineJob(
            cfg=cfg, manifest=manifest,
            log_callback=self.log_handler.push,
            on_complete=self._on_job_complete,
        )
        self._job.start()

    def _on_job_complete(self, ok: bool, message: str, result):
        # Called from the worker thread — bounce onto the main thread.
        self.root.after(0, lambda: self._finish_job(ok, message))

    def _finish_job(self, ok: bool, message: str):
        self.run_btn.config(state=tk.NORMAL)
        self.status.set(("Done. " if ok else "FAILED. ") + message)
        self.log_handler.push(("Done. " if ok else "FAILED. ") + message)


def main():
    """Entry point used by `chipoid-gui` and `python -m chipoid.gui`."""
    root = tk.Tk()
    ChipOidApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
