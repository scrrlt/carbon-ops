"""Static intensity provider implementations."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from carbon_ops.intensity_provider.base import IntensityProvider, IntensityReading


class StaticIntensityProvider(IntensityProvider):
    """Return static intensity values from an in-memory mapping."""

    def __init__(
        self, mapping: Mapping[str, float], default: float, ttl_seconds: int = 3600
    ) -> None:
        super().__init__(ttl_seconds=ttl_seconds)
        self._mapping = dict(mapping)
        self._default = float(default)
        self._version = "static-v1"

    def _get_reading_uncached(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        """Return a static intensity regardless of timestamp.

        Args:
            timestamp: Unused timestamp placeholder.
            region: Region identifier.

        Returns:
            Static intensity reading for the requested region.
        """

        _ = timestamp
        value = self._mapping.get(region, self._default)
        return IntensityReading(
            intensity_gco2_kwh=float(value),
            provider_version=self._version,
        )
