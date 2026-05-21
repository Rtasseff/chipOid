"""Manifest CSV loader.

Manifest schema (one image per row):
    image_id     unique identifier (used for output subdirectory and as a column in the
                 consolidated table)
    source       relative path under `input.data_root` of the input file.
                 - If extract_channels.enabled: a multi-page TIFF to extract from.
                 - Otherwise: the brightfield TIFF directly.
    [anything else]
                 free-form metadata columns (group, condition, dose, replicate, ...)
                 propagate as-is into the consolidated wells table.

The manifest path itself is taken from `config.input.manifest`.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"image_id", "source"}


def validate_manifest(df: pd.DataFrame, *, where: str = "manifest") -> pd.DataFrame:
    """Validate required columns / uniqueness / non-empty image_ids in place.

    Splits out the post-`read_csv` part of `load_manifest` so the GUI can
    validate a DataFrame it built in memory without touching the filesystem.
    Returns the same DataFrame, with stripped column names and required
    columns cast to stripped strings. `where` is the label used in error
    messages (a filename when loaded from disk, "manifest" otherwise).
    """
    df.columns = [c.strip() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{where} missing required column(s): {sorted(missing)}. "
            f"Found: {list(df.columns)}"
        )

    df["image_id"] = df["image_id"].astype(str).str.strip()
    df["source"] = df["source"].astype(str).str.strip()

    if df["image_id"].duplicated().any():
        dupes = df.loc[df["image_id"].duplicated(), "image_id"].tolist()
        raise ValueError(f"{where} has duplicate image_id values: {dupes}")

    if (df["image_id"] == "").any():
        raise ValueError(f"{where} has empty image_id values")

    return df


def load_manifest(path: Path) -> pd.DataFrame:
    """Read manifest CSV and validate required columns / uniqueness."""
    df = pd.read_csv(path)
    return validate_manifest(df, where=str(path))


def metadata_columns(manifest: pd.DataFrame) -> list[str]:
    """Manifest columns other than the two required ones."""
    return [c for c in manifest.columns if c not in REQUIRED_COLUMNS]
