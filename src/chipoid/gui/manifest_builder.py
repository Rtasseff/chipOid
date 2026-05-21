"""Build a chipOid manifest DataFrame from a folder of TIFF files.

Walks `input_dir` looking for `*.tif` / `*.tiff`, separates brightfield bases
from `_<marker>` companions, and returns a DataFrame the pipeline can consume
directly. Optionally enriches each row with parsed filename metadata.

The pipeline accepts `image_id` and `source` as required columns plus any
extra metadata columns. We never produce duplicate image_ids and we never
include companions as their own rows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from . import filename_schema as _fs


TIFF_SUFFIXES = (".tif", ".tiff")


def _is_companion(stem: str, markers: Iterable[str]) -> bool:
    """True if `stem` ends with `_<marker>` (case-insensitive) for any marker."""
    lower = stem.lower()
    for m in markers:
        m = m.strip()
        if m and lower.endswith("_" + m.lower()):
            return True
    return False


def scan_folder_for_images(
    input_dir: Path,
    markers: Iterable[str],
    filename_schema: _fs.FilenameSchema | None = None,
    *,
    data_root: Path | None = None,
) -> pd.DataFrame:
    """Build a manifest DataFrame for chipOid from a folder.

    Args:
      input_dir: folder containing brightfield + optional companion TIFFs.
      markers:   marker names, used to identify (and exclude) companion files
                 and to strip the suffix when deriving image_id.
      filename_schema: when supplied, each base filename is parsed via
                 `filename_schema.parse_basename` and the resulting fields are
                 attached as additional columns. None = no metadata columns.
      data_root: if supplied, `source` paths are stored relative to this dir
                 (so the pipeline resolves them against `cfg.input.data_root`).
                 If None, the GUI sets data_root := input_dir, and source
                 becomes just the filename.

    Returns:
      DataFrame with columns: image_id, source[, <metadata fields ...>].
      Sorted by image_id. May be empty if the folder has no base images
      (caller decides whether to treat that as an error).

    Raises:
      ValueError on duplicate image_ids (which can only happen if files
      collide after marker stripping — e.g. `foo.tif` and `foo_green.tif`
      yielded the same image_id but no brightfield base existed).
    """
    input_dir = Path(input_dir)
    if data_root is None:
        data_root = input_dir
    else:
        data_root = Path(data_root)

    markers = [m.strip() for m in markers if m.strip()]

    # Collect candidate TIFFs (non-recursive — same as SegOid).
    all_tifs: list[Path] = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES
    )

    # A base image is any TIFF whose stem does NOT end with `_<marker>`.
    base_files: list[Path] = [p for p in all_tifs if not _is_companion(p.stem, markers)]

    rows: list[dict] = []
    seen_image_ids: set[str] = set()
    for bf_path in base_files:
        image_id = _fs.derive_image_id(bf_path.name, markers)
        if image_id in seen_image_ids:
            raise ValueError(
                f"duplicate image_id '{image_id}' derived from {bf_path.name}; "
                f"another base file in the folder produced the same id"
            )
        seen_image_ids.add(image_id)

        # Source path relative to data_root (so it matches what the manifest
        # CSV would carry if loaded from disk).
        try:
            rel_source = bf_path.relative_to(data_root).as_posix()
        except ValueError:
            # `data_root` is not an ancestor of `bf_path`; fall back to the
            # absolute path so the pipeline can still find it.
            rel_source = bf_path.as_posix()

        row: dict = {"image_id": image_id, "source": rel_source}

        if filename_schema is not None:
            metadata = _fs.parse_basename(bf_path.name, filename_schema, markers)
            row.update(metadata)

        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("image_id", kind="stable").reset_index(drop=True)
    return df
