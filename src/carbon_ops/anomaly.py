"""Simple anomaly detection utilities (rolling Z-score)."""

from __future__ import annotations

import math
from typing import List, Tuple


def detect_anomalies(
    series: List[float], window: int = 5, z_thresh: float = 3.0
) -> Tuple[bool, float]:
    """
    Return (has_anomaly, z_score) using rolling window mean/std on the tail.

    Uses last `window` points to compute z of the last value.
    If std is zero (flat baseline) and the last value deviates, treat as anomaly with inf z.
    """
    if not series:
        return False, 0.0
    w = max(2, min(window, len(series)))
    tail = series[-w:]
    x = tail[-1]
    if len(tail) == 1:
        return False, 0.0
    mean = sum(tail[:-1]) / (len(tail) - 1)
    var = sum((v - mean) ** 2 for v in tail[:-1]) / (len(tail) - 1)
    std = var**0.5
    if math.isclose(std, 0.0, abs_tol=1e-12):
        if not math.isclose(x, mean, abs_tol=1e-12):
            return True, float("inf")
        return False, 0.0
    z = abs(x - mean) / std
    return z >= z_thresh, z
