"""Carbon estimation package.

Provides the high-level :class:`CarbonEstimator` API along with
supporting utilities for defaults and provider orchestration.
"""

from __future__ import annotations

from .estimator import CarbonEstimator
from .engine import EstimationEngine

__all__ = ["CarbonEstimator", "EstimationEngine"]
