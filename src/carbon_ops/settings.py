"""Environment-backed settings primitives for :mod:`carbon_ops`."""

from __future__ import annotations

import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["CarbonOpsSettings", "get_settings"]


class CarbonOpsSettings(BaseSettings):
    """Expose environment-derived configuration knobs for Carbon Ops.

    The settings class centralises all environment lookups to satisfy the
    security policy requiring :class:`~pydantic_settings.BaseSettings` for
    environment access. All attributes correspond to documented environment
    variables and default to ``None`` (or a sensible inline default) when the
    variable is not present.

    Attributes:
        default_region: Default grid region when configuration is absent.
        default_pue: Default PUE profile or numeric override.
        bucket_minutes: Override for interpolation bucket size in minutes.
        carbon_config_path: Explicit path to the configuration file.
        idle_baseline_watts: Pre-calibrated idle baseline for telemetry.
        calibration_version: Identifier for calibration methodology.
        cpu_tdp_watts: Explicit CPU TDP override for telemetry calculations.
        fallback_embodied_carbon_kg: Embodied carbon fallback value in kg.
        governor_socket_path: Filesystem path to the governor's Unix domain
            socket. When unset the default ``/var/run/carbon-ops.sock`` is
            used.
        governor_request_timeout: Timeout in seconds for governor IPC
            requests.
        electricitymaps_token: Primary ElectricityMaps API token.
        electricitymaps_legacy_token: Legacy ElectricityMaps token alias.
        watttime_username: WattTime username credential.
        watttime_password: WattTime password credential.
        carbon_intensity_file: Optional path to a carbon intensity JSON file.
    """

    default_region: str | None = Field(default=None, alias="DCL_DEFAULT_REGION")
    default_pue: float | str | None = Field(default=None, alias="DCL_PUE_DEFAULT")
    bucket_minutes: int | None = Field(default=None, alias="DCL_BUCKET_MINUTES")
    carbon_config_path: str | None = Field(default=None, alias="CARBON_CONFIG_PATH")
    idle_baseline_watts: float | None = Field(default=None, alias="IDLE_BASELINE_WATTS")
    calibration_version: str = Field(default="v1", alias="CALIBRATION_VERSION")
    cpu_tdp_watts: float | None = Field(default=None, alias="CPU_TDP_WATTS")
    fallback_embodied_carbon_kg: float | None = Field(
        default=None, alias="CARBON_OPS_FALLBACK_EMBODIED_CARBON_KG"
    )
    governor_socket_path: str | None = Field(
        default=None, alias="CARBON_OPS_GOVERNOR_SOCKET"
    )
    governor_request_timeout: float = Field(
        default=0.2, alias="CARBON_OPS_GOVERNOR_TIMEOUT"
    )
    electricitymaps_token: str | None = Field(
        default=None, alias="ELECTRICITYMAPS_TOKEN"
    )
    electricitymaps_legacy_token: str | None = Field(
        default=None, alias="ELECTRICITYMAPS_API_KEY"
    )
    watttime_username: str | None = Field(default=None, alias="WATTTIME_USERNAME")
    watttime_password: str | None = Field(default=None, alias="WATTTIME_PASSWORD")
    carbon_intensity_file: str | None = Field(
        default=None, alias="CARBON_OPS_CARBON_INTENSITY_FILE"
    )

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    @field_validator(
        "idle_baseline_watts",
        "cpu_tdp_watts",
        "fallback_embodied_carbon_kg",
        "governor_request_timeout",
        mode="before",
    )
    @classmethod
    def _parse_optional_float(cls, value: object) -> float | None:
        """Parse optional float fields while tolerating malformed input.

        Args:
            value: Raw environment value.

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

    @field_validator("bucket_minutes", mode="before")
    @classmethod
    def _parse_optional_int(cls, value: object) -> int | None:
        """Parse optional integer fields while tolerating malformed input.

        Args:
            value: Raw environment value.

        Returns:
            Parsed integer when conversion succeeds, otherwise ``None``.
        """

        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    @field_validator("carbon_intensity_file", mode="before")
    @classmethod
    def _fallback_legacy_intensity_file(cls, value: object) -> str | None:
        """Support the legacy ACS environment variable name."""

        if value in (None, ""):
            legacy = os.getenv("ACSE_CARBON_INTENSITY_FILE")
            return legacy or None
        if isinstance(value, str):
            return value
        return str(value)

    @property
    def electricitymaps_effective_token(self) -> str | None:
        """Return the ElectricityMaps token considering legacy aliases.

        Returns:
            The preferred token string when configured, otherwise ``None``.
        """

        return self.electricitymaps_token or self.electricitymaps_legacy_token


def get_settings() -> CarbonOpsSettings:
    """Return a :class:`CarbonOpsSettings` instance.

    Returns:
        Settings parsed from environment variables.
    """

    return CarbonOpsSettings()
