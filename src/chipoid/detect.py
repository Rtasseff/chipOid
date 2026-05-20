"""Stage 1 — Hough-circle detection of candidate well centers.

Pipeline:
    pre-smooth (Gaussian) -> Canny edges -> hough_circle accumulator over a
    radius range -> hough_circle_peaks for non-max suppression.

Returns a DataFrame: x, y, r, score (one row per detection).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from skimage import feature, filters, transform, util


def detect_wells(bf: np.ndarray, *,
                 radius_min: int, radius_max: int, radius_step: int = 1,
                 canny_sigma: float = 2.0,
                 canny_low_threshold: float | None = None,
                 canny_high_threshold: float | None = None,
                 peak_threshold: float = 0.30,
                 min_spacing: int = 110,
                 max_peaks: int = 2000,
                 ) -> tuple[pd.DataFrame, np.ndarray]:
    """Detect circles in a brightfield image.

    Args:
      bf: 2-D array (uint8 preferred). Other dtypes are converted via img_as_ubyte.
      radius_min, radius_max, radius_step: search range for circle radii (px).
      canny_sigma: Gaussian smoothing inside Canny.
      canny_low_threshold, canny_high_threshold: Canny hysteresis thresholds.
        Pass None to use skimage's auto-thresholding.
      peak_threshold: required vote fraction (of global max) to keep a peak.
      min_spacing: minimum (xy) distance between accepted peaks (px).
      max_peaks: hard cap on number of peaks returned.

    Returns:
      (detections, edges):
        detections: DataFrame with columns x, y, r, score
        edges: boolean ndarray of Canny edges (saved for diagnostics)
    """
    if bf.dtype != np.uint8:
        bf = util.img_as_ubyte(bf)
    # Extra pre-smooth on top of Canny's internal blur — helps on 8-bit
    # percentile-stretched brightfield where quantization can produce spurious edges.
    smooth = filters.gaussian(bf, sigma=1.0, preserve_range=True).astype(np.float64) / 255.0
    edges = feature.canny(
        smooth, sigma=canny_sigma,
        low_threshold=canny_low_threshold, high_threshold=canny_high_threshold,
    )

    radii = np.arange(radius_min, radius_max + 1, radius_step)
    hspaces = transform.hough_circle(edges, radii)
    accums, cxs, cys, rs = transform.hough_circle_peaks(
        hspaces, radii,
        min_xdistance=min_spacing,
        min_ydistance=min_spacing,
        threshold=peak_threshold,
        total_num_peaks=max_peaks,
    )
    df = pd.DataFrame({"x": cxs, "y": cys, "r": rs, "score": accums})
    return df, edges
