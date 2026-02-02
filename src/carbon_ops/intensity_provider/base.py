"""Base types and caching logic for carbon intensity providers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IntensityReading:
    """Represents a carbon intensity observation."""

    intensity_gco2_kwh: float
    uncertainty: float | None = None
    provider_version: str | None = None
    calibration_version: str | None = None
    conversion_version: str | None = None


@dataclass(frozen=True, slots=True, eq=False)
class CacheStats:
    """Expose cache hit/miss counters for providers."""

    hits: int
    misses: int

    def to_dict(self) -> dict[str, int]:
        """Return cache statistics as a dictionary."""

        return {"hits": self.hits, "misses": self.misses}

    def __eq__(self, other: object) -> bool:
        """Support equality checks against mappings for compatibility."""

        if isinstance(other, CacheStats):
            return (self.hits, self.misses) == (other.hits, other.misses)
        if isinstance(other, Mapping):
            return other.get("hits") == self.hits and other.get("misses") == self.misses
        return NotImplemented

    def __getitem__(self, key: str) -> int:
        """Provide mapping-style access for compatibility with legacy tests."""

        if key == "hits":
            return self.hits
        if key == "misses":
            return self.misses
        raise KeyError(key)


class IntensityProvider(ABC):
    """Abstract base class implementing TTL caching of provider responses."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl_seconds: Final[int] = ttl_seconds
        self._cache: dict[
            tuple[str | None, str], tuple[float, IntensityReading | None]
        ] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    @abstractmethod
    def _get_reading_uncached(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        """Fetch an intensity reading without consulting the cache."""

    def get_intensity(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        """Return an intensity reading using the built-in TTL cache.

        Args:
            timestamp: Optional timestamp used for cache bucketing.
            region: Provider-specific region identifier.

        Returns:
            An :class:`IntensityReading` instance when available, otherwise
            ``None`` to indicate provider failure.
        """

        cache_key = self._cache_key(timestamp, region)
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached is not None:
            cached_at, reading = cached
            if now - cached_at <= self._ttl_seconds:
                self._cache_hits += 1
                LOGGER.debug(
                    "Intensity cache hit",
                    extra={
                        "provider": type(self).__name__,
                        "region": region,
                        "cache_event": "hit",
                    },
                )
                return reading
            self._cache.pop(cache_key, None)

        self._cache_misses += 1
        LOGGER.debug(
            "Intensity cache miss",
            extra={
                "provider": type(self).__name__,
                "region": region,
                "cache_event": "miss",
            },
        )
        reading = self._get_reading_uncached(timestamp, region)
        self._cache[cache_key] = (now, reading)
        return reading

    def get_cache_stats(self) -> CacheStats:
        """Return cache hit/miss counters.

        Returns:
            Dataclass containing cache hit and miss counters.
        """

        return CacheStats(hits=self._cache_hits, misses=self._cache_misses)

    def _cache_key(
        self, timestamp: datetime | None, region: str
    ) -> tuple[str | None, str]:
        """Return a cache key bucketed at the minute level.

        Args:
            timestamp: Optional timestamp driving the cache bucket.
            region: Region identifier for the cache key.

        Returns:
            Tuple used as the cache key.
        """

        if timestamp is None:
            return (None, region)
        bucket = timestamp.replace(second=0, microsecond=0)
        return (bucket.isoformat(), region)
