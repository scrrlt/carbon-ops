"""Provider orchestration helpers for carbon intensity lookups."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Mapping

from carbon_ops.intensity_provider import (
    ElectricityMapsProvider,
    FallbackIntensityProvider,
    IntensityProvider,
    StaticIntensityProvider,
    UKCarbonIntensityProvider,
    WattTimeProvider,
)

LOGGER = logging.getLogger(__name__)


def build_provider_chain(
    *,
    provider_keys: Iterable[str],
    ttl_seconds: int,
    default_mapping: Mapping[str, float],
) -> IntensityProvider | None:
    """Construct an intensity provider chain.

    Args:
        provider_keys: Ordered collection of provider identifiers.
        ttl_seconds: Cache time-to-live for the provider chain.
        default_mapping: Static mapping used for the fallback provider.

    Returns:
        A configured :class:`IntensityProvider` instance or ``None`` when no
        providers could be initialised.
    """
    providers: list[IntensityProvider] = []
    for raw_key in provider_keys:
        name = raw_key.strip().lower()
        try:
            provider = _build_single_provider(
                name=name, ttl_seconds=ttl_seconds, defaults=default_mapping
            )
        except (ImportError, ValueError, TypeError) as exc:
            LOGGER.warning(
                "Failed to initialise provider '%s' (ttl=%s): %s",
                name,
                ttl_seconds,
                exc,
            )
            continue
        if provider is not None:
            providers.append(provider)

    if not providers:
        return None
    if len(providers) == 1:
        return providers[0]
    return FallbackIntensityProvider(list(providers), ttl_seconds=ttl_seconds)


def _build_single_provider(
    *, name: str, ttl_seconds: int, defaults: Mapping[str, float]
) -> IntensityProvider | None:
    """Build a single provider based on its identifier."""
    if name == "static":
        global_average = float(defaults.get("global-average", 475.0))
        return StaticIntensityProvider(
            mapping=dict(defaults),
            default=global_average,
            ttl_seconds=max(ttl_seconds, 600),
        )
    if name == "wattime":
        return WattTimeProvider(ttl_seconds=ttl_seconds)
    if name == "electricitymaps":
        return ElectricityMapsProvider(ttl_seconds=ttl_seconds)
    if name == "uk":
        return UKCarbonIntensityProvider(ttl_seconds=ttl_seconds)
    LOGGER.warning("Unknown provider key '%s'; skipping", name)
    return None
