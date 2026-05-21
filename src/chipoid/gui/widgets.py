"""Reusable Tkinter widgets for the chipOid GUI.

Adapted from SegOid's `src/gui/widgets.py`. We carry the same idioms:
  - Each widget exposes `.get()` / `.set(value)` to read/write its state.
  - Optional `on_change` callbacks fire whenever the underlying StringVar /
    BooleanVar is written.
  - Widgets pack themselves into their parent; the form module decides the
    enclosing layout.

Additions on top of the SegOid set:
  - LabeledSpinbox: numeric spinbox with min/max/step, int OR float-typed.
  - NoteLabel: small gray text shown beneath a row, used for inline option docs.
  - MetricsCheckGroup: checkbox group for chipOid's per-marker metrics.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Optional


# --------------------------------------------------------------------------- #
# Pickers
# --------------------------------------------------------------------------- #
class FolderPicker(ttk.Frame):
    """Label + Entry + Browse button for selecting a folder."""

    def __init__(
        self,
        parent,
        label: str,
        initial_path: str = "",
        on_change: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)
        self.on_change = on_change
        self.path = tk.StringVar(value=initial_path)
        self.path.trace_add("write", self._on_path_change)

        self.label = ttk.Label(self, text=label, width=20, anchor="e")
        self.label.pack(side=tk.LEFT, padx=(0, 5))
        self.entry = ttk.Entry(self, textvariable=self.path, width=50)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.browse_btn = ttk.Button(self, text="Browse...", command=self._browse, width=10)
        self.browse_btn.pack(side=tk.LEFT)

    def _browse(self):
        initial_dir = self.path.get() or None
        folder = filedialog.askdirectory(
            title=f"Select {self.label.cget('text').strip(':')}",
            initialdir=initial_dir,
        )
        if folder:
            self.path.set(folder)

    def _on_path_change(self, *_args):
        if self.on_change:
            self.on_change(self.path.get())

    def get(self) -> str: return self.path.get()
    def set(self, value: str): self.path.set(value)
    def is_valid(self) -> bool:
        p = Path(self.path.get())
        return bool(self.path.get()) and p.exists() and p.is_dir()


# --------------------------------------------------------------------------- #
# Form rows
# --------------------------------------------------------------------------- #
class LabeledEntry(ttk.Frame):
    """Inline label + Entry for text/number input."""

    def __init__(
        self,
        parent,
        label: str,
        initial_value: str = "",
        width: int = 20,
        on_change: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)
        self.on_change = on_change
        self.value = tk.StringVar(value=initial_value)
        self.value.trace_add("write", self._on_value_change)
        self.label = ttk.Label(self, text=label, width=22, anchor="e")
        self.label.pack(side=tk.LEFT, padx=(0, 5))
        self.entry = ttk.Entry(self, textvariable=self.value, width=width)
        self.entry.pack(side=tk.LEFT)

    def _on_value_change(self, *_args):
        if self.on_change:
            self.on_change(self.value.get())

    def get(self) -> str: return self.value.get()
    def set(self, value: str): self.value.set(str(value) if value is not None else "")


class LabeledSpinbox(ttk.Frame):
    """Label + Spinbox bounded by `min_value`/`max_value` with step `increment`.

    `is_float=False` (default) → integer; True → float with format string.
    """

    def __init__(
        self,
        parent,
        label: str,
        initial_value: float | int,
        min_value: float | int,
        max_value: float | int,
        increment: float | int = 1,
        width: int = 10,
        is_float: bool = False,
    ):
        super().__init__(parent)
        self.is_float = is_float
        self.value = tk.StringVar(value=str(initial_value))
        self.label = ttk.Label(self, text=label, width=22, anchor="e")
        self.label.pack(side=tk.LEFT, padx=(0, 5))
        self.spin = tk.Spinbox(
            self, from_=min_value, to=max_value, increment=increment,
            textvariable=self.value, width=width,
            format=("%.3f" if is_float else None),
        )
        self.spin.pack(side=tk.LEFT)

    def get(self) -> str: return self.value.get()
    def set(self, value): self.value.set(str(value))


class LabeledCombobox(ttk.Frame):
    """Label + Combobox accepting both preset values and free-text typing."""

    def __init__(
        self,
        parent,
        label: str,
        initial_value: str,
        values: list[str],
        width: int = 12,
    ):
        super().__init__(parent)
        self.value = tk.StringVar(value=initial_value)
        self.label = ttk.Label(self, text=label, width=22, anchor="e")
        self.label.pack(side=tk.LEFT, padx=(0, 5))
        self.combo = ttk.Combobox(self, textvariable=self.value, values=values, width=width)
        self.combo.pack(side=tk.LEFT)

    def get(self) -> str: return self.value.get()
    def set(self, value: str): self.value.set(str(value))


class CheckboxOption(ttk.Frame):
    """A labeled checkbox. Optional `on_change(bool)` callback."""

    def __init__(
        self,
        parent,
        label: str,
        initial_value: bool = False,
        on_change: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__(parent)
        self.on_change = on_change
        self.value = tk.BooleanVar(value=initial_value)
        self.value.trace_add("write", self._on_value_change)
        self.checkbox = ttk.Checkbutton(self, text=label, variable=self.value)
        self.checkbox.pack(side=tk.LEFT)

    def _on_value_change(self, *_args):
        if self.on_change:
            self.on_change(self.value.get())

    def get(self) -> bool: return self.value.get()
    def set(self, value: bool): self.value.set(bool(value))


class NoteLabel(ttk.Label):
    """Small gray text shown under a row, used for inline option notes."""

    def __init__(self, parent, text: str):
        super().__init__(parent, text=text, foreground="#666666",
                         wraplength=720, justify=tk.LEFT, font=("TkDefaultFont", 8))


# --------------------------------------------------------------------------- #
# Per-marker metrics checkbox group
# --------------------------------------------------------------------------- #
class MetricsCheckGroup(ttk.Frame):
    """One Checkbutton per metric, with a description on the right.

    `metric_descriptions` is a dict metric -> description string. `defaults`
    is a list of metric names to check by default.
    """

    def __init__(
        self,
        parent,
        metric_descriptions: dict[str, str],
        defaults: list[str],
    ):
        super().__init__(parent)
        self.vars: dict[str, tk.BooleanVar] = {}
        for metric, desc in metric_descriptions.items():
            row = ttk.Frame(self)
            row.pack(fill=tk.X, anchor=tk.W)
            v = tk.BooleanVar(value=(metric in defaults))
            self.vars[metric] = v
            cb = ttk.Checkbutton(row, text=metric, variable=v, width=18)
            cb.pack(side=tk.LEFT, anchor=tk.W)
            note = ttk.Label(row, text=desc, foreground="#444444",
                             wraplength=520, justify=tk.LEFT,
                             font=("TkDefaultFont", 8))
            note.pack(side=tk.LEFT, anchor=tk.W, padx=(4, 0))

    def get(self) -> dict[str, bool]:
        return {m: v.get() for m, v in self.vars.items()}

    def set(self, enabled: list[str]):
        enabled_set = set(enabled)
        for m, v in self.vars.items():
            v.set(m in enabled_set)


# --------------------------------------------------------------------------- #
# Log display
# --------------------------------------------------------------------------- #
class ScrolledText(ttk.Frame):
    """tk.Text + scrollbar; convenience `append` / `clear` methods."""

    def __init__(self, parent, height: int = 12, width: int = 100, readonly: bool = True):
        super().__init__(parent)
        self.text = tk.Text(self, height=height, width=width, wrap=tk.NONE,
                            state=tk.DISABLED if readonly else tk.NORMAL,
                            font=("TkFixedFont", 9))
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.config(yscrollcommand=self.scrollbar.set)

    def append(self, text: str):
        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, text)
        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete(1.0, tk.END)
        self.text.config(state=tk.DISABLED)
