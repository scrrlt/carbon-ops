"""Fallback chaining provider for carbon intensity lookups."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

import httpx

from carbon_ops.intensity_provider.base import IntensityProvider, IntensityReading

LOGGER = logging.getLogger(__name__)


class FallbackIntensityProvider(IntensityProvider):
    """Try a sequence of providers until one succeeds."""

    def __init__(
        self, providers: Iterable[IntensityProvider], ttl_seconds: int = 300
    ) -> None:
        super().__init__(ttl_seconds=ttl_seconds)
        self._providers = tuple(providers)
        self._version = "fallback-v1"

    def _get_reading_uncached(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        """Return the first successful reading from the provider chain.

        Args:
            timestamp: Optional timestamp forwarded to providers.
            region: Region identifier forwarded to providers.

        Returns:
            The first successful reading from the provider chain, otherwise
            ``None`` when all providers fail.
        """

        for provider in self._providers:
            try:
                reading = provider.get_intensity(timestamp, region)
            except (ValueError, ConnectionError, httpx.HTTPError) as exc:
                LOGGER.warning(
                    "Fallback provider invocation failed",
                    extra={
                        "provider": type(provider).__name__,
                        "region": region,
                        "error_type": type(exc).__name__,
                    },
                    exc_info=exc,
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning(
                    "Fallback provider unexpected failure",
                    extra={
                        "provider": type(provider).__name__,
                        "region": region,
                        "error_type": type(exc).__name__,
                    },
                    exc_info=exc,
                )
                continue

            if reading is not None:
                return reading
        return None
