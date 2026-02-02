"""UK National Grid carbon intensity provider."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

import httpx

from carbon_ops.intensity_provider.base import IntensityProvider, IntensityReading

LOGGER = logging.getLogger(__name__)


class UKCarbonIntensityProvider(IntensityProvider):
    """Fetch national carbon intensity data published by the UK grid."""

    def __init__(
        self,
        base_url: str = "https://api.carbonintensity.org.uk",
        ttl_seconds: int = 300,
        *,
        timeout_seconds: float = 8.0,
    ) -> None:
        super().__init__(ttl_seconds=ttl_seconds)
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._version = "uk-ci-v2"

    def _get_reading_uncached(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        """Fetch the latest UK carbon intensity forecast or actual value.

        Args:
            timestamp: Unused timestamp placeholder.
            region: Region identifier (ignored because the API is national).

        Returns:
            An intensity reading when successful, otherwise ``None``.
        """

        _ = timestamp
        url = f"{self._base}/intensity"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                payload: object = response.json()
        except httpx.HTTPStatusError as exc:
            LOGGER.warning(
                "UK Carbon Intensity HTTP error",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "status_code": exc.response.status_code,
                    "url": url,
                },
                exc_info=exc,
            )
            return None
        except httpx.HTTPError as exc:
            LOGGER.warning(
                "UK Carbon Intensity transport error",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
                exc_info=exc,
            )
            return None
        except (ValueError, TypeError) as exc:
            LOGGER.warning(
                "UK Carbon Intensity response parsing error",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
                exc_info=exc,
            )
            return None

        payload_dict = _normalize_mapping(payload)
        entries_obj = payload_dict.get("data") if payload_dict is not None else None
        if not isinstance(entries_obj, list) or not entries_obj:
            LOGGER.warning(
                "UK Carbon Intensity response missing data",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
            )
            return None

        entries_list = cast(list[object], entries_obj)
        first_entry = entries_list[0]
        first_entry_dict = _normalize_mapping(first_entry)
        if first_entry_dict is None:
            LOGGER.warning(
                "UK Carbon Intensity returned malformed entry",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
            )
            return None

        intensity_block = _normalize_mapping(first_entry_dict.get("intensity"))
        if intensity_block is None:
            LOGGER.warning(
                "UK Carbon Intensity missing intensity block",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
            )
            return None

        value_candidate = intensity_block.get("forecast")
        if value_candidate is None:
            value_candidate = intensity_block.get("actual")
        value = _coerce_float(value_candidate)
        if value is None:
            LOGGER.warning(
                "UK Carbon Intensity returned non-numeric intensity",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                    "value": str(value_candidate),
                },
            )
            return None

        if value <= 0:
            LOGGER.warning(
                "UK Carbon Intensity reported non-positive intensity",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                    "value": value,
                },
            )
            return None

        return IntensityReading(
            intensity_gco2_kwh=value,
            provider_version=self._version,
        )


def _coerce_float(value: object | None) -> float | None:
    """Attempt to convert ``value`` to ``float`` while tolerating errors.

    Args:
        value: Raw value sourced from the API payload.

    Returns:
        Parsed float when conversion succeeds, otherwise ``None``.
    """

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _normalize_mapping(value: object | None) -> dict[str, object] | None:
    """Return a dictionary with string keys when possible.

    Args:
        value: Raw value produced by ``json`` parsing.

    Returns:
        Mapping with string keys ready for further processing, or ``None`` when
        the input cannot be represented as such.
    """

    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    value_dict = cast(dict[object, object], value)
    normalized: dict[str, object] = {}
    for key_obj, item in value_dict.items():
        if isinstance(key_obj, str):
            normalized[key_obj] = item
    return normalized
