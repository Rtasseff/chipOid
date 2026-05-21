"""Filename → metadata parsing for chipOid.

Companion images live next to their brightfield with a `_<marker>` suffix.
When the user enables "Parse filenames into metadata fields", chipOid splits
the filename's <base> on `_` and labels each chunk per the user's schema.

Two-step API mirrors the SegOid implementation:
  - parse_filename(basename, schema)   — pure splitting, no marker stripping
  - parse_basename(filename, schema, markers)
                                       — wrapper that strips .tif / .tiff and
                                         a known marker suffix before parsing

The chipOid wrapper is needed because a base file `mcf7_media.tif` and its
companion `mcf7_media_green.tif` share the same physical base ("mcf7_media");
without stripping `_green` first, the companion would create a spurious
metadata field called "green".

create_schema_from_labels cleans user-typed labels (lowercase, strip
non-identifier chars, fall back to `field_N` if empty). Matches SegOid so
behavior is identical for users who've used both tools.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class FilenameSchema:
    """Schema for parsing filenames split on `delimiter`."""

    delimiter: str = "_"
    field_names: list[str] = field(default_factory=list)


def create_schema_from_labels(
    labels: Iterable[str],
    delimiter: str = "_",
) -> FilenameSchema:
    """Build a FilenameSchema from user-typed labels.

    Cleaning rules (matches SegOid):
      - Strip whitespace.
      - Lowercase.
      - Drop non-`[a-zA-Z0-9_]` characters.
      - If the cleaned label is empty, fall back to `field_N` where N is the
        position in the list.
    """
    cleaned: list[str] = []
    for label in labels:
        clean = re.sub(r"[^a-zA-Z0-9_]", "", label.strip().lower())
        if not clean:
            clean = f"field_{len(cleaned)}"
        cleaned.append(clean)
    return FilenameSchema(delimiter=delimiter, field_names=cleaned)


def parse_filename(basename: str, schema: FilenameSchema) -> dict[str, str]:
    """Split `basename` on the schema delimiter and label each chunk.

    Chunks beyond the schema's `field_names` get auto-named `field_N`. An
    empty schema returns `{}` (no metadata).
    """
    if not basename:
        return {}
    chunks = basename.split(schema.delimiter)
    if not schema.field_names and len(chunks) == 1:
        # Nothing to split — no metadata to produce.
        return {}
    result: dict[str, str] = {}
    for i, chunk in enumerate(chunks):
        if i < len(schema.field_names):
            name = schema.field_names[i]
        else:
            name = f"field_{i}"
        result[name] = chunk
    return result


# Tail extensions we strip before parsing. lower-cased; matching is case-insensitive.
_KNOWN_EXTENSIONS = (".tif", ".tiff")


def _strip_extension(name: str) -> str:
    lower = name.lower()
    for ext in _KNOWN_EXTENSIONS:
        if lower.endswith(ext):
            return name[: -len(ext)]
    return name


def _strip_marker_suffix(base: str, markers: Iterable[str]) -> str:
    """If `base` ends with `_<marker>` (case-insensitive) for any marker in
    `markers`, strip that suffix. First match wins. Returns the stripped base.
    Empty markers list = no stripping."""
    lower = base.lower()
    for m in markers:
        m = m.strip()
        if not m:
            continue
        suffix = "_" + m.lower()
        if lower.endswith(suffix):
            return base[: -len(suffix)]
    return base


def parse_basename(
    filename: str,
    schema: FilenameSchema,
    markers: Iterable[str],
) -> dict[str, str]:
    """Parse `filename` into metadata.

    Steps:
      1. Strip `.tif` or `.tiff` (case-insensitive).
      2. Strip any trailing `_<marker>` (case-insensitive) for known markers.
         This collapses brightfield and companions to the same base before
         parsing — otherwise the companion's `_green` would become a metadata
         field.
      3. Split on the schema delimiter and label per `parse_filename`.

    Returns the metadata dict (possibly empty).
    """
    stripped = _strip_extension(filename)
    stripped = _strip_marker_suffix(stripped, markers)
    return parse_filename(stripped, schema)


def derive_image_id(filename: str, markers: Iterable[str]) -> str:
    """Return the canonical `image_id` for an input filename.

    Strips extension and any trailing `_<marker>` suffix. Used by the
    manifest builder so a brightfield and its companions agree on the same
    image_id.
    """
    return _strip_marker_suffix(_strip_extension(filename), markers)
