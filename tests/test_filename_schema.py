"""Tests for chipoid.gui.filename_schema (pure logic, no Tk)."""
from __future__ import annotations

import pytest

from chipoid.gui.filename_schema import (
    FilenameSchema,
    create_schema_from_labels,
    derive_image_id,
    parse_basename,
    parse_filename,
)


# --------------------------------------------------------------------------- #
# parse_filename (the plain split function)
# --------------------------------------------------------------------------- #
def test_parse_filename_assigns_labels_in_order():
    schema = FilenameSchema(delimiter="_", field_names=["plate", "well"])
    assert parse_filename("A01_B02", schema) == {"plate": "A01", "well": "B02"}


def test_parse_filename_extra_chunks_get_field_n_names():
    schema = FilenameSchema(delimiter="_", field_names=["cell", "cond"])
    assert parse_filename("mcf7_media_high_dose_rep1", schema) == {
        "cell": "mcf7",
        "cond": "media",
        "field_2": "high",
        "field_3": "dose",
        "field_4": "rep1",
    }


def test_parse_filename_with_no_underscores_and_empty_schema_returns_empty():
    # If there's nothing to split AND no labels, nothing useful comes out.
    assert parse_filename("solo", FilenameSchema()) == {}


def test_parse_filename_with_no_underscores_and_a_label_assigns_field_0():
    schema = FilenameSchema(field_names=["plate"])
    assert parse_filename("solo", schema) == {"plate": "solo"}


# --------------------------------------------------------------------------- #
# parse_basename (chipOid wrapper that strips ext + marker first)
# --------------------------------------------------------------------------- #
def test_parse_basename_strips_tif_extension():
    schema = FilenameSchema(field_names=["cell", "cond"])
    assert parse_basename("mcf7_media.tif", schema, markers=["green", "red"]) == {
        "cell": "mcf7", "cond": "media",
    }


def test_parse_basename_strips_tiff_extension_case_insensitive():
    schema = FilenameSchema(field_names=["cell", "cond"])
    assert parse_basename("mcf7_media.TIFF", schema, markers=["green", "red"]) == {
        "cell": "mcf7", "cond": "media",
    }


def test_parse_basename_strips_marker_suffix_before_parsing():
    schema = FilenameSchema(field_names=["cell", "cond"])
    # The companion file's _green must NOT become a metadata field.
    assert parse_basename("mcf7_media_green.tif", schema, markers=["green", "red"]) == {
        "cell": "mcf7", "cond": "media",
    }


def test_parse_basename_marker_match_is_case_insensitive():
    schema = FilenameSchema(field_names=["cell"])
    assert parse_basename("mcf7_GREEN.tif", schema, markers=["green"]) == {"cell": "mcf7"}


def test_parse_basename_with_no_matching_marker_keeps_suffix():
    schema = FilenameSchema(field_names=["cell", "cond", "extra"])
    # "blue" isn't in markers, so it's parsed as a normal chunk.
    assert parse_basename("mcf7_media_blue.tif", schema, markers=["green", "red"]) == {
        "cell": "mcf7", "cond": "media", "extra": "blue",
    }


def test_parse_basename_with_empty_schema_uses_field_n_labels():
    # An empty schema with underscores in the basename produces field_N
    # columns — matches SegOid's behavior. This is the path the GUI takes when
    # filename parsing is enabled but the user gave no labels.
    assert parse_basename(
        "anything_at_all.tif", FilenameSchema(), markers=["green"]
    ) == {"field_0": "anything", "field_1": "at", "field_2": "all"}


def test_parse_basename_empty_schema_single_chunk_returns_empty_dict():
    # Special case: no schema AND no underscores → nothing to add.
    assert parse_basename("solo.tif", FilenameSchema(), markers=["green"]) == {}


# --------------------------------------------------------------------------- #
# create_schema_from_labels (label sanitization)
# --------------------------------------------------------------------------- #
def test_create_schema_strips_whitespace_and_lowercases():
    s = create_schema_from_labels(["  Plate  ", "Well", "Time"])
    assert s.field_names == ["plate", "well", "time"]


def test_create_schema_drops_special_characters():
    # "well-1?" should clean to "well1" (alphanumeric + underscore only).
    s = create_schema_from_labels(["plate", "well-1?", "dose%"])
    assert s.field_names == ["plate", "well1", "dose"]


def test_create_schema_empty_labels_get_field_n():
    s = create_schema_from_labels(["plate", "  ", "dose"])
    assert s.field_names == ["plate", "field_1", "dose"]


def test_create_schema_default_delimiter_is_underscore():
    s = create_schema_from_labels(["a", "b"])
    assert s.delimiter == "_"


# --------------------------------------------------------------------------- #
# derive_image_id
# --------------------------------------------------------------------------- #
def test_derive_image_id_strips_extension_and_marker():
    assert derive_image_id("mcf7_media.tif", markers=["green", "red"]) == "mcf7_media"
    assert derive_image_id("mcf7_media_green.tif", markers=["green", "red"]) == "mcf7_media"
    assert derive_image_id("mcf7_media_red.tif", markers=["green", "red"]) == "mcf7_media"


def test_derive_image_id_no_marker_match_keeps_stem():
    assert derive_image_id("foo_bar.tif", markers=["green"]) == "foo_bar"


def test_derive_image_id_empty_markers_just_strips_extension():
    assert derive_image_id("anything_with_underscores.TIF", markers=[]) == "anything_with_underscores"
