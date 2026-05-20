"""Optional preprocessing: split a multi-page TIFF into one brightfield + N companions.

Page → channel mapping comes from config.input.extract_channels.pages.

Brightfield handling: always converted to 8-bit via per-image percentile
stretching (clip to [p1, p99], scale to 0..255). This is required because the
downstream Canny defaults assume an 8-bit dynamic range; higher-bit-depth BF
would need manual Canny threshold tuning that we don't expose. The stretch is
PER IMAGE — absolute intensities are not preserved across images. That is
fine because the brightfield is only used for *geometry* (finding the wells),
never for quantification.

Companion (fluorescence) channels are written through as their NATIVE dtype
(typically uint16). Absolute intensity matters for these, so we never rescale
or clip them — what's in the raw file is what gets measured.

Output naming follows the project-wide companion convention:
    <out_dir>/<image_id>.tif                — brightfield (8-bit)
    <out_dir>/<image_id>_<marker>.tif       — one per marker (native dtype)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile


# Hardcoded percentile clip for BF 8-bit conversion. These values are what's
# been tested; the 1% / 99% choice rejects extreme outliers (saturated pixels,
# dust specks, dead pixels) without losing real signal range.
BF_CLIP_PERCENTILES = (1.0, 99.0)


def _bf_to_uint8(arr: np.ndarray) -> np.ndarray:
    """Per-image clip-and-stretch from any dtype to uint8 [0, 255].

    Step 1 — outlier rejection: compute p1 and p99 of pixel values; pixels below
    p1 will become 0, pixels above p99 will become 255.
    Step 2 — linear stretch: map [p1, p99] -> [0, 255].

    Why both steps in one function: a single saturated pixel at the sensor max
    would, without clipping, compress the rest of the image into a tiny range
    when we linearly stretch to 0..255. Clipping protects against that.
    """
    lo_pct, hi_pct = BF_CLIP_PERCENTILES
    lo, hi = np.percentile(arr, [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1
    out = np.clip((arr.astype(np.float32) - lo) / (hi - lo), 0.0, 1.0)
    return (out * 255).astype(np.uint8)


def extract_one(raw_path: Path, image_id: str, out_dir: Path,
                pages: dict[str, int], markers: list[str]) -> dict[str, Path]:
    """Extract pages from a multi-page TIFF; write one TIFF per channel.

    Args:
      raw_path: path to multi-page TIFF
      image_id: stem to use for output filenames
      out_dir:  directory to write into (created if needed)
      pages:    dict mapping channel name -> 0-based page index. Must include
                'brightfield' and every name in `markers`.
      markers:  ordered list of marker names

    Returns:
      dict mapping channel name to the written file path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    with tifffile.TiffFile(raw_path) as tif:
        n_pages = len(tif.pages)
        required_pages = {pages["brightfield"], *(pages[m] for m in markers)}
        max_required = max(required_pages)
        if max_required >= n_pages:
            raise ValueError(
                f"{raw_path}: needs page {max_required} but file has only {n_pages} pages"
            )

        # Brightfield: always 8-bit via clip-and-stretch (see module docstring).
        bf = tif.pages[pages["brightfield"]].asarray()
        bf8 = _bf_to_uint8(bf)
        bf_path = out_dir / f"{image_id}.tif"
        tifffile.imwrite(bf_path, bf8, photometric="minisblack")
        written["brightfield"] = bf_path

        # Companions: written through verbatim (native dtype, no scaling).
        for m in markers:
            arr = tif.pages[pages[m]].asarray()
            p = out_dir / f"{image_id}_{m}.tif"
            tifffile.imwrite(p, arr, photometric="minisblack")
            written[m] = p

    return written
