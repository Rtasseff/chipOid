"""ConfigForm — Tk form that builds every chipOid config option as a widget.

Layout: one `ttk.LabelFrame` per section (Markers, Filename parsing, Extract,
Detection, Lattice, Readout, Output figures). Each option row is widget +
small NoteLabel underneath.

For testing, the pure validation/coercion logic lives in
`config_form_logic.coerce_raw_values`. This module just calls into it after
collecting widget values.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from . import config_form_logic as logic
from .widgets import (
    CheckboxOption,
    LabeledCombobox,
    LabeledEntry,
    LabeledSpinbox,
    MetricsCheckGroup,
    NoteLabel,
)


# Display strings that appear next to each option. Kept here so it's easy to
# scan the user-facing notes in one place.
NOTES: dict[str, str] = {
    "markers": "Comma-separated marker names (e.g. green, red). Each marker M needs a companion file <base>_M.tif next to each brightfield.",
    "parse_filenames": "When on, each brightfield basename (after stripping _<marker> and the extension) is split on '_' and each chunk becomes a metadata column on the manifest. Extra chunks beyond your labels get field_0, field_1, …",
    "filename_labels": "Comma-separated field labels in the order they appear in the filename. Whitespace and special characters are stripped; empty labels get 'field_N'.",
    "extract_enabled": "Enable only if your raw input is a multi-page TIFF (brightfield on page 0, markers on subsequent pages). Output goes to output/<image_id>/; data_root is read-only.",
    "extract_pages": "0-based page index inside the multi-page TIFF. Update after changing the markers list above.",
    "radius_min": "Smallest well radius (px) the Hough search will look for.",
    "radius_max": "Largest well radius (px) the Hough search will look for.",
    "radius_step": "Sweep increment between min and max radii. Larger = faster, coarser.",
    "canny_sigma": "Gaussian smoothing applied before edge detection. Increase for noisy BF; decrease for sharp images.",
    "canny_low_threshold": "Lower edge-detection threshold. Leave blank for skimage auto (10% of dtype max — assumes 8-bit BF).",
    "canny_high_threshold": "Upper edge-detection threshold. Leave blank for skimage auto (20% of dtype max).",
    "peak_threshold": "Minimum vote fraction (of global max) to accept a Hough peak. Lower finds more wells but increases false positives.",
    "min_spacing": "Minimum pixel distance between accepted peaks. Set < well pitch but > well diameter.",
    "max_peaks": "Hard cap on number of detections per image.",
    "lattice_enabled": "Fit a grid to the detections and fill in missing wells. Turn off to use raw Hough detections only.",
    "k_nn": "Nearest neighbors used to estimate row/col pitch.",
    "axis_band": "Off-axis tolerance (px) when binning neighbor vectors into row vs col.",
    "snap_tolerance": "Max distance (px) between a grid point and the nearest detection before the point is marked 'filled' instead of 'detected'.",
    "rotation_deg": "'auto' = estimate rotation from data; or a number in degrees (CCW positive). Use 0 to force pure axis-aligned.",
    "min_detected_fraction": "Trim any row/col with fewer than this fraction of real detections. 0 disables trimming.",
    "max_rows": "Hard cap on lattice rows after trimming. Leave blank for no cap.",
    "max_cols": "Hard cap on lattice columns after trimming. Leave blank for no cap.",
    "margin": "Pixels to shrink the signal disk inward from the fitted well radius.",
    "annulus_inner": "Background annulus inner offset from r_well (px).",
    "annulus_outer": "Background annulus outer offset from r_well (px). Must exceed inner.",
    "per_image_subdir": "When on, each image's outputs land in output/<image_id>/. Turn off only for single-image runs.",
    "save_review_figure": "Composite per-image overview PNG: BF + lattice + intensities + scatter.",
    "save_stage_overlays": "Individual stage PNGs: Canny, Hough overlay, lattice overlay, intensity overlays.",
    "save_diagnostics": "Per-image histogram + scatter diagnostic PNGs.",
}


def _row(parent, widget, note: str):
    """Pack a widget row above a NoteLabel describing it. Returns the widget."""
    widget.pack(fill=tk.X, anchor=tk.W, pady=(4, 0))
    if note:
        NoteLabel(parent, text=note).pack(fill=tk.X, anchor=tk.W, padx=(20, 0), pady=(0, 2))
    return widget


class ConfigForm:
    """Builds the chipOid config form inside a parent frame and reads it back."""

    def __init__(self, parent: tk.Misc):
        self.parent = parent

        # --- Section: Markers + Filename parsing ------------------------- #
        markers_frame = ttk.LabelFrame(parent, text="Markers + Filename parsing", padding=8)
        markers_frame.pack(fill=tk.X, pady=4)
        self.markers = _row(markers_frame,
                            LabeledEntry(markers_frame, "markers", "green, red", width=40),
                            NOTES["markers"])
        self.parse_filenames = _row(markers_frame,
                                    CheckboxOption(markers_frame,
                                                   "Parse filenames into metadata fields",
                                                   initial_value=False,
                                                   on_change=self._on_parse_toggle),
                                    NOTES["parse_filenames"])
        self.filename_labels_frame = ttk.Frame(markers_frame)
        self.filename_labels = LabeledEntry(self.filename_labels_frame,
                                            "field labels", "plate, well, dose, replicate", width=40)
        self.filename_labels.pack(fill=tk.X, anchor=tk.W, pady=(2, 0))
        NoteLabel(self.filename_labels_frame, text=NOTES["filename_labels"]).pack(
            fill=tk.X, anchor=tk.W, padx=(20, 0))
        # Initially hidden until parse_filenames is checked.

        # --- Section: Extract channels ----------------------------------- #
        extract_frame = ttk.LabelFrame(parent, text="Extract channels (multi-page raw TIFF input)", padding=8)
        extract_frame.pack(fill=tk.X, pady=4)
        self.extract_enabled = _row(extract_frame,
                                    CheckboxOption(extract_frame,
                                                   "Enable channel extraction",
                                                   initial_value=False,
                                                   on_change=self._on_extract_toggle),
                                    NOTES["extract_enabled"])
        self.extract_pages_frame = ttk.Frame(extract_frame)
        NoteLabel(extract_frame, text=NOTES["extract_pages"]).pack(
            fill=tk.X, anchor=tk.W, padx=(20, 0))
        self.extract_pages: dict[str, LabeledSpinbox] = {}
        # The brightfield page widget is always present (when extract is enabled);
        # marker page widgets are regenerated whenever markers change.
        # Build initial widgets — will be rebuilt on demand.
        self._rebuild_extract_pages()

        # Wire markers change → rebuild extract page widgets if extraction is on.
        self.markers.value.trace_add("write", lambda *a: self._on_markers_changed())

        # --- Section: Detection ----------------------------------------- #
        det = ttk.LabelFrame(parent, text="Detection (Hough circle finder)", padding=8)
        det.pack(fill=tk.X, pady=4)
        self.radius_min = _row(det, LabeledSpinbox(det, "radius_min (px)", 35, 1, 500), NOTES["radius_min"])
        self.radius_max = _row(det, LabeledSpinbox(det, "radius_max (px)", 50, 1, 500), NOTES["radius_max"])
        self.radius_step = _row(det, LabeledSpinbox(det, "radius_step", 1, 1, 20), NOTES["radius_step"])
        self.canny_sigma = _row(det, LabeledSpinbox(det, "canny_sigma", 2.0, 0.1, 10.0, 0.1, is_float=True), NOTES["canny_sigma"])
        self.canny_low = _row(det, LabeledEntry(det, "canny_low_threshold", "", width=12), NOTES["canny_low_threshold"])
        self.canny_high = _row(det, LabeledEntry(det, "canny_high_threshold", "", width=12), NOTES["canny_high_threshold"])
        self.peak_threshold = _row(det, LabeledSpinbox(det, "peak_threshold", 0.30, 0.0, 1.0, 0.01, is_float=True), NOTES["peak_threshold"])
        self.min_spacing = _row(det, LabeledSpinbox(det, "min_spacing (px)", 110, 1, 1000), NOTES["min_spacing"])
        self.max_peaks = _row(det, LabeledSpinbox(det, "max_peaks", 2000, 1, 100000, 100), NOTES["max_peaks"])

        # --- Section: Lattice ------------------------------------------- #
        lat = ttk.LabelFrame(parent, text="Lattice (axis-aligned grid fit + fill)", padding=8)
        lat.pack(fill=tk.X, pady=4)
        self.lattice_enabled = _row(lat, CheckboxOption(lat, "Enable lattice fit", initial_value=True), NOTES["lattice_enabled"])
        self.k_nn = _row(lat, LabeledSpinbox(lat, "k_nn", 4, 1, 12), NOTES["k_nn"])
        self.axis_band = _row(lat, LabeledSpinbox(lat, "axis_band (px)", 50.0, 1.0, 200.0, 1.0, is_float=True), NOTES["axis_band"])
        self.snap_tolerance = _row(lat, LabeledSpinbox(lat, "snap_tolerance (px)", 30.0, 1.0, 200.0, 1.0, is_float=True), NOTES["snap_tolerance"])
        self.rotation_deg = _row(lat, LabeledCombobox(lat, "rotation_deg", "auto", ["auto", "0", "0.5", "-0.5"], width=12), NOTES["rotation_deg"])
        self.min_detected_fraction = _row(lat, LabeledSpinbox(lat, "min_detected_fraction", 0.25, 0.0, 1.0, 0.05, is_float=True), NOTES["min_detected_fraction"])
        self.max_rows = _row(lat, LabeledEntry(lat, "max_rows", "", width=12), NOTES["max_rows"])
        self.max_cols = _row(lat, LabeledEntry(lat, "max_cols", "", width=12), NOTES["max_cols"])

        # --- Section: Readout ------------------------------------------- #
        ro = ttk.LabelFrame(parent, text="Readout (per-well sampling)", padding=8)
        ro.pack(fill=tk.X, pady=4)
        self.margin = _row(ro, LabeledSpinbox(ro, "margin (px)", 4.0, 0.0, 50.0, 0.5, is_float=True), NOTES["margin"])
        self.annulus_inner = _row(ro, LabeledSpinbox(ro, "annulus_inner (px)", 8.0, 0.0, 100.0, 0.5, is_float=True), NOTES["annulus_inner"])
        self.annulus_outer = _row(ro, LabeledSpinbox(ro, "annulus_outer (px)", 20.0, 0.0, 200.0, 0.5, is_float=True), NOTES["annulus_outer"])

        metrics_label = ttk.Label(ro, text="Metrics (columns to emit per marker):",
                                  anchor=tk.W, font=("TkDefaultFont", 9, "bold"))
        metrics_label.pack(fill=tk.X, anchor=tk.W, pady=(8, 2))
        self.metrics = MetricsCheckGroup(
            ro,
            metric_descriptions=logic.metric_descriptions(),
            defaults=["mean", "median", "std", "bg_median", "signal", "signal_median",
                      "n_signal_px", "n_bg_px", "partial_disk"],
        )
        self.metrics.pack(fill=tk.X, anchor=tk.W, padx=(20, 0))

        # --- Section: Output figures ------------------------------------ #
        out = ttk.LabelFrame(parent, text="Output figures", padding=8)
        out.pack(fill=tk.X, pady=4)
        self.per_image_subdir = _row(out, CheckboxOption(out, "Per-image output subdir", initial_value=True), NOTES["per_image_subdir"])
        self.save_review_figure = _row(out, CheckboxOption(out, "Save review composite figure", initial_value=True), NOTES["save_review_figure"])
        self.save_stage_overlays = _row(out, CheckboxOption(out, "Save per-stage overlays", initial_value=True), NOTES["save_stage_overlays"])
        self.save_diagnostics = _row(out, CheckboxOption(out, "Save histogram + scatter diagnostics", initial_value=True), NOTES["save_diagnostics"])

    # ------------------------------------------------------------------ #
    # Dynamic UI helpers
    # ------------------------------------------------------------------ #
    def _on_parse_toggle(self, enabled: bool) -> None:
        if enabled:
            self.filename_labels_frame.pack(fill=tk.X, anchor=tk.W, padx=(20, 0), pady=(2, 0))
        else:
            self.filename_labels_frame.pack_forget()

    def _on_extract_toggle(self, enabled: bool) -> None:
        if enabled:
            self.extract_pages_frame.pack(fill=tk.X, anchor=tk.W, padx=(20, 0), pady=(2, 0))
        else:
            self.extract_pages_frame.pack_forget()

    def _on_markers_changed(self) -> None:
        # Only rebuild if the extract section is even visible.
        if self.extract_enabled.get():
            self._rebuild_extract_pages()

    def _rebuild_extract_pages(self) -> None:
        # Preserve any values the user already set so we don't reset them on a
        # marker-list edit (only add/remove widgets that changed).
        previous = {ch: w.get() for ch, w in self.extract_pages.items()}
        for child in self.extract_pages_frame.winfo_children():
            child.destroy()
        self.extract_pages.clear()

        channels = ["brightfield"]
        marker_text = self.markers.get() if hasattr(self, "markers") else "green, red"
        channels.extend(tok.strip() for tok in marker_text.split(",") if tok.strip())

        for i, ch in enumerate(channels):
            initial = previous.get(ch, i)
            spin = LabeledSpinbox(self.extract_pages_frame, f"page for '{ch}'",
                                  int(initial) if str(initial).isdigit() else i,
                                  0, 100)
            spin.pack(fill=tk.X, anchor=tk.W, pady=2)
            self.extract_pages[ch] = spin

    # ------------------------------------------------------------------ #
    # Read state
    # ------------------------------------------------------------------ #
    def raw_values(self) -> dict[str, Any]:
        """Collect widget values as a dict that `coerce_raw_values` understands."""
        extract_pages = {ch: w.get() for ch, w in self.extract_pages.items()} \
            if self.extract_enabled.get() else {"brightfield": 0}
        return {
            "markers": self.markers.get(),
            "extract_enabled": self.extract_enabled.get(),
            "extract_pages": extract_pages,
            "radius_min": self.radius_min.get(),
            "radius_max": self.radius_max.get(),
            "radius_step": self.radius_step.get(),
            "canny_sigma": self.canny_sigma.get(),
            "canny_low_threshold": self.canny_low.get(),
            "canny_high_threshold": self.canny_high.get(),
            "peak_threshold": self.peak_threshold.get(),
            "min_spacing": self.min_spacing.get(),
            "max_peaks": self.max_peaks.get(),
            "lattice_enabled": self.lattice_enabled.get(),
            "k_nn": self.k_nn.get(),
            "axis_band": self.axis_band.get(),
            "snap_tolerance": self.snap_tolerance.get(),
            "rotation_deg": self.rotation_deg.get(),
            "min_detected_fraction": self.min_detected_fraction.get(),
            "max_rows": self.max_rows.get(),
            "max_cols": self.max_cols.get(),
            "margin": self.margin.get(),
            "annulus_inner": self.annulus_inner.get(),
            "annulus_outer": self.annulus_outer.get(),
            "metrics": self.metrics.get(),
            "per_image_subdir": self.per_image_subdir.get(),
            "save_review_figure": self.save_review_figure.get(),
            "save_stage_overlays": self.save_stage_overlays.get(),
            "save_diagnostics": self.save_diagnostics.get(),
        }

    def parse_filenames_enabled(self) -> bool:
        return self.parse_filenames.get()

    def filename_label_text(self) -> str:
        return self.filename_labels.get()

    def to_cfg_overrides(self) -> dict[str, Any]:
        """Return validated config-override dict (to be deep-merged on defaults)."""
        return logic.coerce_raw_values(self.raw_values())
