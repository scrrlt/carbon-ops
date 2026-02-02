"""WattTime MOER provider."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from carbon_ops.intensity_provider.base import IntensityProvider, IntensityReading
from carbon_ops.settings import CarbonOpsSettings, get_settings

LOGGER = logging.getLogger(__name__)


class WattTimeProvider(IntensityProvider):
    """Fetch marginal operating emission rate (MOER) data from WattTime."""

    def __init__(
        self,
        base_url: str = "https://api2.watttime.org",
        ttl_seconds: int = 300,
        *,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float = 8.0,
        settings: CarbonOpsSettings | None = None,
    ) -> None:
        super().__init__(ttl_seconds=ttl_seconds)
        self._base = base_url.rstrip("/")
        self._explicit_username = username
        self._explicit_password = password
        self._settings = settings
        self._timeout = timeout_seconds
        self._version = "watttime-v2"

    def _get_reading_uncached(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        """Fetch the latest MOER value for the specified balancing authority.

        Args:
            timestamp: Unused timestamp placeholder.
            region: Balancing authority code supported by WattTime.

        Returns:
            An intensity reading when successful, otherwise ``None``.
        """

        _ = timestamp
        username, password = self._resolve_credentials()
        if not username or not password:
            LOGGER.warning(
                "WattTime credentials not configured",
                extra={"provider": type(self).__name__, "region": region},
            )
            return None

        url = f"{self._base}/v2/moer?ba={region}"
        try:
            with httpx.Client(
                timeout=self._timeout,
                auth=(username, password),
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            LOGGER.warning(
                "WattTime HTTP error",
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
                "WattTime transport error",
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
                "WattTime response parsing error",
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
                "WattTime unexpected error",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                },
                exc_info=exc,
            )
            return None

        lb_per_mwh_raw = payload.get("moer")
        try:
            lb_per_mwh = float(lb_per_mwh_raw)
        except (TypeError, ValueError) as exc:
            LOGGER.warning(
                "WattTime returned non-numeric intensity",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                    "value": lb_per_mwh_raw,
                },
                exc_info=exc,
            )
            return None

        if lb_per_mwh <= 0:
            LOGGER.warning(
                "WattTime reported non-positive intensity",
                extra={
                    "provider": type(self).__name__,
                    "region": region,
                    "url": url,
                    "value": lb_per_mwh,
                },
            )
            return None

        gco2_per_kwh = 0.453592 * lb_per_mwh
        return IntensityReading(
            intensity_gco2_kwh=gco2_per_kwh,
            provider_version=self._version,
            conversion_version="lbMWh_to_gkWh@0.453592",
        )

    def _resolve_credentials(self) -> tuple[str | None, str | None]:
        settings_obj = self._settings or get_settings()
        username = self._explicit_username or settings_obj.watttime_username
        password = self._explicit_password or settings_obj.watttime_password
        return username, password
