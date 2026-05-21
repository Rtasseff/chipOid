"""Tests for chipoid.gui.manifest_builder."""
from __future__ import annotations

from pathlib import Path

import pytest

from chipoid.gui.filename_schema import FilenameSchema
from chipoid.gui.manifest_builder import scan_folder_for_images


def _touch(p: Path):
    """Create an empty file at `p`, mkdir-ing parents if needed."""
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")


# --------------------------------------------------------------------------- #
# Happy-path manifest building
# --------------------------------------------------------------------------- #
def test_excludes_companions_from_manifest(tmp_path):
    _touch(tmp_path / "a.tif")
    _touch(tmp_path / "a_green.tif")
    _touch(tmp_path / "a_red.tif")
    _touch(tmp_path / "b.tif")

    df = scan_folder_for_images(tmp_path, markers=["green", "red"])
    assert sorted(df["image_id"].tolist()) == ["a", "b"]
    assert list(df.columns) == ["image_id", "source"]


def test_sources_relative_to_data_root(tmp_path):
    _touch(tmp_path / "a.tif")
    df = scan_folder_for_images(tmp_path, markers=["green"], data_root=tmp_path)
    assert df.loc[0, "source"] == "a.tif"


def test_filename_schema_attaches_metadata_columns(tmp_path):
    _touch(tmp_path / "mcf7_media.tif")
    _touch(tmp_path / "mcf7_media_green.tif")
    _touch(tmp_path / "mcf7_drug.tif")

    schema = FilenameSchema(field_names=["cell", "cond"])
    df = scan_folder_for_images(tmp_path, markers=["green", "red"], filename_schema=schema)

    assert "cell" in df.columns
    assert "cond" in df.columns
    row_media = df.set_index("image_id").loc["mcf7_media"]
    assert row_media["cell"] == "mcf7"
    assert row_media["cond"] == "media"
    row_drug = df.set_index("image_id").loc["mcf7_drug"]
    assert row_drug["cell"] == "mcf7"
    assert row_drug["cond"] == "drug"


def test_companion_metadata_not_attached(tmp_path):
    # Even if filename parsing is on, companion files must not become rows.
    _touch(tmp_path / "mcf7_media.tif")
    _touch(tmp_path / "mcf7_media_green.tif")  # would parse to (mcf7, media) — same as base
    schema = FilenameSchema(field_names=["cell", "cond"])
    df = scan_folder_for_images(tmp_path, markers=["green"], filename_schema=schema)
    assert len(df) == 1
    assert df.loc[0, "image_id"] == "mcf7_media"


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #
def test_empty_folder_returns_empty_dataframe(tmp_path):
    df = scan_folder_for_images(tmp_path, markers=["green"])
    assert df.empty


def test_only_companions_no_base_returns_empty(tmp_path):
    _touch(tmp_path / "a_green.tif")
    _touch(tmp_path / "a_red.tif")
    df = scan_folder_for_images(tmp_path, markers=["green", "red"])
    assert df.empty


def test_missing_companion_is_not_an_error_at_manifest_time(tmp_path):
    # The pipeline warns at runtime if a companion is missing. The manifest
    # builder should NOT raise just because a marker file is absent.
    _touch(tmp_path / "a.tif")
    _touch(tmp_path / "a_green.tif")
    # no a_red.tif on purpose
    df = scan_folder_for_images(tmp_path, markers=["green", "red"])
    assert df["image_id"].tolist() == ["a"]


def test_tif_and_tiff_both_recognized(tmp_path):
    _touch(tmp_path / "a.tif")
    _touch(tmp_path / "b.TIFF")
    df = scan_folder_for_images(tmp_path, markers=["green"])
    assert sorted(df["image_id"].tolist()) == ["a", "b"]


def test_non_tif_files_ignored(tmp_path):
    _touch(tmp_path / "a.tif")
    _touch(tmp_path / "readme.txt")
    _touch(tmp_path / "ignore.png")
    df = scan_folder_for_images(tmp_path, markers=["green"])
    assert df["image_id"].tolist() == ["a"]


def test_duplicate_image_ids_raise(tmp_path):
    # Two base files that resolve to the same image_id after marker stripping
    # would create a duplicate. Construct that by giving an empty markers list
    # (so marker stripping is a no-op) and two files with the same stem in
    # different extensions.
    _touch(tmp_path / "x.tif")
    _touch(tmp_path / "x.TIFF")
    with pytest.raises(ValueError, match="duplicate image_id"):
        scan_folder_for_images(tmp_path, markers=["green"])
