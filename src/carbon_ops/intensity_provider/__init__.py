"""Carbon intensity provider implementations and abstractions."""

from __future__ import annotations

from carbon_ops.intensity_provider.base import (
    CacheStats,
    IntensityProvider,
    IntensityReading,
)
from carbon_ops.intensity_provider.electricitymaps import ElectricityMapsProvider
from carbon_ops.intensity_provider.fallback import FallbackIntensityProvider
from carbon_ops.intensity_provider.static import StaticIntensityProvider
from carbon_ops.intensity_provider.uk import UKCarbonIntensityProvider
from carbon_ops.intensity_provider.watttime import WattTimeProvider

__all__ = [
    "CacheStats",
    "ElectricityMapsProvider",
    "FallbackIntensityProvider",
    "IntensityProvider",
    "IntensityReading",
    "StaticIntensityProvider",
    "UKCarbonIntensityProvider",
    "WattTimeProvider",
]
