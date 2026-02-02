"""ElectricityMaps v3 API provider."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from carbon_ops.intensity_provider.base import IntensityProvider, IntensityReading
from carbon_ops.settings import CarbonOpsSettings, get_settings

LOGGER = logging.getLogger(__name__)


class ElectricityMapsProvider(IntensityProvider):
    """Fetch real-time carbon intensity data from the ElectricityMaps API."""

    def __init__(
        self,
        base_url: str = "https://api.electricitymap.org/v3",
        ttl_seconds: int = 300,
        *,
        token: str | None = None,
        timeout_seconds: float = 8.0,
        settings: CarbonOpsSettings | None = None,
    ) -> None:
        super().__init__(ttl_seconds=ttl_seconds)
        self._base = base_url.rstrip("/")
        self._explicit_token = token
        self._settings = settings
        self._timeout = timeout_seconds
        self._version = "emaps-v3"

    def _get_reading_uncached(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        """Fetch the most recent intensity for the specified region.

        Args:
            timestamp: Unused timestamp placeholder.
            region: Zone identifier supported by ElectricityMaps.

        Returns:
            An intensity reading when successful, otherwise ``None``.
        """

        _ = timestamp
        token = self._resolve_token()
        if not token:
            LOGGER.warning(
                "ElectricityMaps token not configured",
                extra={"provider": type(self).__name__, "region": region},
            )
            return None

        url = f"{self._base}/carbon-intensity/latest?zone={region}"
        headers = {"auth-token": token}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            LOGGER.warning(
                "ElectricityMaps HTTP error",
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
                "ElectricityMaps transport error",
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
                "ElectricityMaps response parsing error",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
                exc_info=exc,
            )
            return None
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning(
                "ElectricityMaps unexpected error",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
                exc_info=exc,
            )
            return None

        intensity_raw = payload.get("carbonIntensity") or payload.get("intensity")
        try:
            intensity_value = float(intensity_raw)
        except (TypeError, ValueError) as exc:
            LOGGER.warning(
                "ElectricityMaps returned non-numeric intensity",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                    "value": intensity_raw,
                },
                exc_info=exc,
            )
            return None

        if intensity_value <= 0:
            LOGGER.warning(
                "ElectricityMaps reported non-positive intensity",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                    "value": intensity_value,
                },
            )
            return None

        return IntensityReading(
            intensity_gco2_kwh=float(intensity_value),
            provider_version=self._version,
        )

    def _resolve_token(self) -> str | None:
        settings_obj = self._settings or get_settings()
        if self._explicit_token:
            return self._explicit_token
        return settings_obj.electricitymaps_effective_token
