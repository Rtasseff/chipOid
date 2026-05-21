"""Integration test for the in-memory pipeline entry point.

Exercises `chipoid.pipeline.run_batch_in_memory` against the seeded
`data/mcf7_media.tif` (+ companions) using an in-memory manifest DataFrame.
This is the canary for the refactor in pipeline.py: GUI invocation path
must produce the same artifacts the CLI does.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from chipoid.config import load_config
from chipoid.pipeline import run_batch_in_memory


# All tests in this file require the seeded data on disk.
DATA_ROOT = Path("data")
SEED_BF = DATA_ROOT / "mcf7_media.tif"
SEED_GREEN = DATA_ROOT / "mcf7_media_green.tif"
SEED_RED = DATA_ROOT / "mcf7_media_red.tif"


pytestmark = pytest.mark.skipif(
    not (SEED_BF.exists() and SEED_GREEN.exists() and SEED_RED.exists()),
    reason="seeded mcf7_media.tif + companions not present under data/",
)


def test_run_batch_in_memory_produces_outputs(tmp_path):
    cfg = load_config(None)  # pure defaults — exhaustive validation
    cfg["input"]["data_root"] = str(DATA_ROOT)
    cfg["output"]["dir"] = str(tmp_path)

    manifest = pd.DataFrame([{
        "image_id": "mcf7_media",
        "source": "mcf7_media.tif",
        # An extra metadata column to confirm propagation into wells_all.csv.
        "condition": "control_test",
    }])

    log_lines: list[str] = []
    result = run_batch_in_memory(cfg, manifest, log=log_lines.append)

    assert result["n_images"] == 1
    assert result["n_success"] == 1
    assert result["n_failed"] == 0

    # Per-image outputs
    per_image_dir = tmp_path / "mcf7_media"
    assert per_image_dir.is_dir()
    assert (per_image_dir / "wells.csv").exists()

    # Consolidated CSV (with manifest metadata propagated)
    wells_all = tmp_path / "wells_all.csv"
    assert wells_all.exists()
    df = pd.read_csv(wells_all)
    assert "condition" in df.columns
    assert (df["condition"] == "control_test").all()
    # Sanity-check the canonical 100-well result from the seed image.
    assert len(df) == 100

    # Batch summary
    assert (tmp_path / "batch_summary.csv").exists()

    # Log callback was actually exercised
    assert len(log_lines) > 0
    assert any("mcf7_media" in line for line in log_lines)
