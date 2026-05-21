"""Batch orchestrator. Reads config + manifest, runs each image end-to-end,
writes per-image artifacts and consolidated batch CSVs.

Two entry points:
  - run_batch(config_path): the CLI entry point. Loads a YAML config + CSV
    manifest from disk, then delegates to run_batch_in_memory.
  - run_batch_in_memory(cfg, manifest, log): the in-memory entry point used
    by the GUI. The GUI builds its own config dict and manifest DataFrame
    from widget state + folder scan, and passes a log callback that pushes
    messages into the GUI's log queue.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import tifffile

from .config import load_config
from .detect import detect_wells
from .extract import extract_one
from .lattice import fit_lattice
from .manifest import load_manifest, metadata_columns, validate_manifest
from .readout import attach_metrics, measure_marker, preflight
from . import viz


@dataclass
class ImageResult:
    image_id: str
    wells: pd.DataFrame      # per-well rows
    summary: dict[str, Any]  # one-row metadata for batch summary


def _resolve_input_paths(row: pd.Series, cfg: dict, data_root: Path,
                         per_image_out_dir: Path
                         ) -> tuple[Path, dict[str, Path], bool]:
    """Return (brightfield_path, {marker: companion_path}, was_extracted).

    Runs the optional extraction step if config.input.extract_channels.enabled.
    When extracting, output files land in `per_image_out_dir` (the per-image
    output directory) alongside the overlays, NOT in a shared data subdir —
    extraction is per-run output, not per-batch cached input.
    """
    image_id = row["image_id"]
    source = data_root / row["source"]
    if not source.exists():
        raise FileNotFoundError(f"[{image_id}] source not found: {source}")

    ex_cfg = cfg["input"]["extract_channels"]
    if ex_cfg["enabled"]:
        written = extract_one(
            raw_path=source,
            image_id=image_id,
            out_dir=per_image_out_dir,
            pages=ex_cfg["pages"],
            markers=cfg["markers"],
        )
        bf_path = written["brightfield"]
        marker_paths = {m: written[m] for m in cfg["markers"]}
        was_extracted = True
    else:
        # Source IS the brightfield. Companions by convention: <stem>_<marker>.tif
        bf_path = source
        stem = source.stem
        marker_paths = {m: source.parent / f"{stem}_{m}.tif" for m in cfg["markers"]}
        was_extracted = False

    return bf_path, marker_paths, was_extracted


def process_image(row: pd.Series, cfg: dict, data_root: Path, out_root: Path,
                  log) -> ImageResult:
    image_id = row["image_id"]
    log(f"=== {image_id} ===")

    # Per-image output dir
    if cfg["output"]["per_image_subdir"]:
        out_dir = out_root / image_id
    else:
        out_dir = out_root
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve / extract inputs. Extracted files (if extraction is enabled) land
    # in this image's output directory alongside the overlays.
    bf_path, marker_paths, was_extracted = _resolve_input_paths(
        row, cfg, data_root, per_image_out_dir=out_dir
    )
    bf = tifffile.imread(bf_path)
    log(f"  bf: {bf_path} shape={bf.shape} dtype={bf.dtype}")
    if bf.dtype != np.uint8:
        log(f"  [WARN] BF is {bf.dtype}, not uint8. Canny defaults assume 8-bit; "
            f"set detection.canny_low_threshold / canny_high_threshold explicitly "
            f"or use extract_channels.enabled=true for automatic 8-bit conversion.")

    # Stage 1 — Hough detection
    det_cfg = cfg["detection"]
    centers, edges = detect_wells(
        bf,
        radius_min=det_cfg["radius_min"], radius_max=det_cfg["radius_max"],
        radius_step=det_cfg["radius_step"],
        canny_sigma=det_cfg["canny_sigma"],
        canny_low_threshold=det_cfg["canny_low_threshold"],
        canny_high_threshold=det_cfg["canny_high_threshold"],
        peak_threshold=det_cfg["peak_threshold"],
        min_spacing=det_cfg["min_spacing"],
        max_peaks=det_cfg["max_peaks"],
    )
    log(f"  hough: {len(centers)} detections, r median={centers.r.median():.1f}")

    if cfg["output"]["save_stage_overlays"]:
        viz.save_canny(edges, out_dir / "01_canny.png", det_cfg["canny_sigma"])
        viz.save_hough_overlay(bf, centers, out_dir / "02_hough_overlay.png",
                               (det_cfg["radius_min"], det_cfg["radius_max"]))
    centers.to_csv(out_dir / "hough_centers.csv", index=False)

    # Stage 2 — Lattice
    lat_cfg = cfg["lattice"]
    if lat_cfg["enabled"]:
        wells, lat_info = fit_lattice(
            centers, bf.shape,
            k_nn=lat_cfg["k_nn"],
            axis_band=lat_cfg["axis_band"],
            snap_tolerance=lat_cfg["snap_tolerance"],
            rotation_deg=lat_cfg.get("rotation_deg", "auto"),
            min_detected_fraction=lat_cfg.get("min_detected_fraction", 0.25),
            max_rows=lat_cfg.get("max_rows"),
            max_cols=lat_cfg.get("max_cols"),
        )
        log(f"  lattice: col={lat_info['col_pitch']:.0f} row={lat_info['row_pitch']:.0f}, "
            f"rotation={lat_info['rotation_deg']:+.3f}° ({lat_info['rotation_source']}), "
            f"{lat_info['n_detected']} detected + {lat_info['n_filled']} filled "
            f"(trimmed {lat_info['n_trimmed']} from {lat_info['n_before_trim']})")
        if lat_info.get("trimmed_rows"):
            log(f"    dropped rows: {lat_info['trimmed_rows']}")
        if lat_info.get("trimmed_cols"):
            log(f"    dropped cols: {lat_info['trimmed_cols']}")
        if cfg["output"]["save_stage_overlays"]:
            viz.save_lattice_overlay(bf, wells, out_dir / "03_lattice_overlay.png", lat_info)
    else:
        wells = centers.copy()
        wells.insert(0, "well_id", [f"d{i:04d}" for i in range(len(wells))])
        wells["row"] = -1; wells["col"] = -1; wells["source"] = "detected"
        wells["dist_to_det"] = 0.0
        lat_info = {"col_pitch": float("nan"), "row_pitch": float("nan"),
                    "x0": float("nan"), "y0": float("nan"),
                    "default_r": float(centers.r.median()),
                    "n_grid": len(wells), "n_detected": len(wells), "n_filled": 0}

    wells = wells.reset_index(drop=True)

    # Stage 3 — Readout
    r_well = float(lat_info["default_r"])
    margin = cfg["readout"]["margin"]
    ai = cfg["readout"]["annulus_inner"]; ao = cfg["readout"]["annulus_outer"]
    requested_metrics = cfg["readout"]["metrics"]

    pf = preflight(wells, r_well, margin, ai, ao, bf.shape)
    for w in pf["warnings"]:
        log(f"  [WARN] {w}")
    log(f"  readout geometry: signal_r={pf['r_signal']:.0f}, "
        f"bg=[{pf['r_in']:.0f},{pf['r_out']:.0f}], "
        f"expected signal_px≈{pf['expected_signal_px']:.0f}")

    marker_signals: dict[str, np.ndarray] = {}
    for marker, mpath in marker_paths.items():
        if not mpath.exists():
            log(f"  [WARN] missing companion {marker}: {mpath}; skipping")
            continue
        img = tifffile.imread(mpath)
        if img.shape != bf.shape:
            raise SystemExit(
                f"[{image_id}] shape mismatch for marker '{marker}': "
                f"bf={bf.shape} vs companion={img.shape}"
            )
        m = measure_marker(img, wells, r_well, margin, ai, ao)
        attach_metrics(wells, marker, m, requested_metrics)
        marker_signals[marker] = m["signal"]
        log(f"  {marker}: signal median={np.nanmedian(m['signal']):.1f} "
            f"p5={np.nanpercentile(m['signal'],5):.1f} "
            f"p95={np.nanpercentile(m['signal'],95):.1f}")

        if cfg["output"]["save_stage_overlays"]:
            viz.save_intensity_overlay(
                bf, wells, m["signal"], out_dir / f"04_intensity_{marker}.png",
                title=f"{marker}: signal (mean - bg, 16-bit)",
                label=f"signal ({marker})",
            )

    # Diagnostics
    if cfg["output"]["save_diagnostics"] and marker_signals:
        viz.save_histograms(
            wells,
            {m: f"signal_{m}" for m in marker_signals},
            out_dir / "06_histograms.png",
        )
        markers_list = list(marker_signals.keys())
        if len(markers_list) >= 2:
            m1, m2 = markers_list[:2]
            viz.save_scatter(
                wells, f"signal_{m1}", f"signal_{m2}",
                f"{m1} signal", f"{m2} signal",
                out_dir / "07_scatter.png",
            )

    # Composite review
    if cfg["output"]["save_review_figure"] and marker_signals:
        viz.save_review_figure(
            bf, wells, marker_signals,
            out_dir / "review.png",
            image_id=image_id, lattice_info=lat_info, n_hough=len(centers),
        )

    # Per-image CSV
    wells.insert(0, "image_id", image_id)
    for col in metadata_columns(pd.DataFrame([row])):
        wells[col] = row[col]
    wells.to_csv(out_dir / "wells.csv", index=False)

    # Optionally delete the extracted TIFFs now that readout is done. The
    # check `was_extracted` ensures we never delete user-supplied source files
    # — only files we ourselves wrote during this run's extraction step.
    if was_extracted and not cfg["output"].get("keep_extracted", True):
        for p in [bf_path, *marker_paths.values()]:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        log(f"  removed extracted files (keep_extracted=false)")

    # Per-image summary row for batch_summary.csv
    summary = {
        "image_id": image_id,
        "n_hough": int(len(centers)),
        "n_wells": int(len(wells)),
        "n_detected": int(lat_info["n_detected"]),
        "n_filled": int(lat_info["n_filled"]),
        "col_pitch": lat_info["col_pitch"],
        "row_pitch": lat_info["row_pitch"],
        "median_radius": r_well,
    }
    for marker, sig in marker_signals.items():
        sig_f = sig[np.isfinite(sig)]
        if len(sig_f):
            summary[f"signal_{marker}_p5"] = float(np.percentile(sig_f, 5))
            summary[f"signal_{marker}_median"] = float(np.median(sig_f))
            summary[f"signal_{marker}_p95"] = float(np.percentile(sig_f, 95))

    return ImageResult(image_id=image_id, wells=wells, summary=summary)


def run_batch(config_path: Path) -> dict:
    """CLI entry point: load config + manifest from disk, then delegate."""
    cfg = load_config(config_path)

    config_dir = config_path.parent
    manifest_path = Path(cfg["input"]["manifest"])
    if not manifest_path.is_absolute():
        cand = config_dir / manifest_path
        if cand.exists():
            manifest_path = cand
    manifest = load_manifest(manifest_path)

    return run_batch_in_memory(cfg, manifest, log=None, config_label=str(config_path))


def run_batch_in_memory(
    cfg: dict,
    manifest: pd.DataFrame,
    log: Callable[[str], None] | None = None,
    *,
    config_label: str = "<in-memory>",
) -> dict:
    """Core implementation. Process every row of `manifest` using `cfg`.

    Args:
      cfg:           already-validated config dict (e.g. from `load_config`).
      manifest:      already-validated manifest DataFrame (e.g. from
                     `load_manifest` or `manifest.validate_manifest`).
      log:           optional message sink (msg: str) called from THIS thread.
                     The GUI passes a callable that pushes onto a queue.Queue.
                     If None, falls back to print() + writing run.log.
      config_label:  label shown in the opening log line. The CLI sets this to
                     the YAML path; the GUI can set its own identifier.

    Returns: same dict as the old run_batch:
      {"n_images", "n_success", "n_failed", "out_root"}.
    """
    manifest = validate_manifest(manifest.copy(), where="manifest")

    data_root = Path(cfg["input"]["data_root"])
    out_root = Path(cfg["output"]["dir"]); out_root.mkdir(parents=True, exist_ok=True)

    # Logging plumbing:
    #   - If `log` was supplied (GUI), use it directly. We ALSO open run.log so
    #     post-mortem debugging via the file is unaffected.
    #   - If `log` is None (CLI default), use print + run.log just like before.
    log_path = out_root / "run.log"
    log_fh = open(log_path, "w")
    if log is None:
        def _log(msg: str) -> None:
            print(msg)
            log_fh.write(msg + "\n"); log_fh.flush()
    else:
        external_log = log
        def _log(msg: str) -> None:
            external_log(msg)
            log_fh.write(msg + "\n"); log_fh.flush()

    _log(f"chipOid batch: {len(manifest)} images, config={config_label}, "
         f"data_root={data_root}, out_root={out_root}")

    # Dump the EFFECTIVE merged config so the user can always see exactly what
    # values were used (defaults + their overrides combined).
    import yaml as _yaml
    _log("effective config (defaults + your overrides):\n"
         + "\n".join("  " + ln for ln in
                     _yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False).splitlines()))

    all_wells: list[pd.DataFrame] = []
    summaries: list[dict] = []
    failures: list[tuple[str, str]] = []

    for _, row in manifest.iterrows():
        try:
            result = process_image(row, cfg, data_root, out_root, _log)
            all_wells.append(result.wells)
            summaries.append(result.summary)
        except Exception as e:
            import traceback as _tb
            _log(f"  [ERROR] {row['image_id']}: {e!r}")
            _log(_tb.format_exc())
            failures.append((row["image_id"], repr(e)))

    if all_wells:
        consolidated = pd.concat(all_wells, ignore_index=True)
        out_csv = out_root / cfg["output"]["consolidated_csv"]
        consolidated.to_csv(out_csv, index=False)
        _log(f"\nconsolidated wells: {out_csv}  ({len(consolidated)} rows)")

    if summaries:
        summary_df = pd.DataFrame(summaries)
        summary_path = out_root / cfg["output"]["batch_summary_csv"]
        summary_df.to_csv(summary_path, index=False)
        _log(f"batch summary:     {summary_path}")

    if failures:
        _log(f"\n{len(failures)} image(s) failed:")
        for image_id, err in failures:
            _log(f"  - {image_id}: {err}")

    log_fh.close()
    return {
        "n_images": len(manifest),
        "n_success": len(summaries),
        "n_failed": len(failures),
        "out_root": str(out_root),
    }
