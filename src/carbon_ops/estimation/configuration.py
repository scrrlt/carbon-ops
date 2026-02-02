"""Runtime configuration utilities for :mod:`carbon_ops.estimation`.

This module centralises the logic that derives effective runtime settings for
:class:`~carbon_ops.estimation.estimator.CarbonEstimator`. It reconciles user
input, configuration files, and static defaults into a strict, typed structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

from carbon_ops.estimation.providers import build_provider_chain
from carbon_ops.intensity_provider import IntensityProvider

if TYPE_CHECKING:
    from carbon_ops.config_loader import CarbonConfig

__all__ = ["EstimatorRuntimeConfig", "build_runtime_config"]


def _extract_config_region(config: CarbonConfig | None) -> str | None:
    if config is None:
        return None
    try:
        return getattr(config.region, "default", None)
    except AttributeError:
        return None


def _extract_config_bucket(config: CarbonConfig | None, default_bucket: int) -> int:
    if config is None:
        return default_bucket
    try:
        value = getattr(config.interpolation, "bucket_minutes", default_bucket)
        return int(value)
    except (AttributeError, TypeError, ValueError):
        return default_bucket


def _extract_config_pue_default(config: CarbonConfig | None) -> float | str | None:
    if config is None:
        return None
    try:
        return getattr(config.pue, "default", None)
    except AttributeError:
        return None


def _resolve_region(configured: str | None, config_region: str | None) -> str:
    if configured and configured != "global-average":
        return configured
    return config_region or "global-average"


def _resolve_pue(
    *,
    datacenter_type: str,
    config_default: float | str | None,
    pue_values: Mapping[str, float],
) -> float:
    if isinstance(config_default, (float, int)):
        return float(config_default)
    profile = datacenter_type or (
        config_default if isinstance(config_default, str) else "cloud-hyperscale"
    )
    return pue_values.get(profile, pue_values["cloud-hyperscale"])


def _build_provider_from_config(
    config: CarbonConfig | None,
    default_mapping: Mapping[str, float],
) -> IntensityProvider | None:
    if config is None:
        return None
    try:
        order = list(getattr(config.providers, "order", []) or [])
        ttl = int(getattr(config.providers, "ttl_seconds", 300) or 300)
    except (AttributeError, TypeError, ValueError):
        return None
    return build_provider_chain(
        provider_keys=order,
        ttl_seconds=ttl,
        default_mapping=default_mapping,
    )


def _resolve_missing_policy(config: CarbonConfig | None) -> str:
    if config is None:
        return "step"
    try:
        policy = getattr(config.interpolation, "missing_policy", "step")
    except AttributeError:
        return "step"
    return str(policy or "step")


@dataclass(slots=True, frozen=True)
class EstimatorRuntimeConfig:
    """Aggregated runtime settings for the carbon estimator.

    Attributes:
        region: Default geographic region used for static intensity lookups.
        datacenter_type: Logical data-centre profile that drives default PUE.
        carbon_intensity_gco2_kwh: Static fallback intensity in gCO2/kWh.
        pue: Effective power usage effectiveness applied to energy inputs.
        missing_policy: Behaviour for missing intensity buckets (``"step"`` or
            ``"drop"``).
        bucket_minutes: Default interpolation bucket size in minutes.
        intensity_provider: Optional chained intensity provider instance.
    """

    region: str
    datacenter_type: str
    carbon_intensity_gco2_kwh: float
    pue: float
    missing_policy: str
    bucket_minutes: int
    intensity_provider: IntensityProvider | None


def build_runtime_config(
    *,
    region: str | None,
    datacenter_type: str,
    custom_carbon_intensity: float | None,
    custom_pue: float | None,
    intensity_provider: IntensityProvider | None,
    config: CarbonConfig | None,
    carbon_intensity_mapping: Mapping[str, float],
    pue_values: Mapping[str, float],
    default_bucket_minutes: int = 15,
) -> EstimatorRuntimeConfig:
    """Resolve effective runtime configuration for the estimator.

    Args:
        region: Explicit region override supplied by the caller.
        datacenter_type: Declared data-centre profile (e.g., ``"cloud-hyperscale"``).
        custom_carbon_intensity: Explicit intensity override in gCO2/kWh.
        custom_pue: Explicit PUE override. When unset, defaults are derived from
            ``datacenter_type`` and configuration.
        intensity_provider: Pre-built intensity provider chain supplied by the
            caller. If ``None`` the configuration is used to build one.
        config: Optional typed configuration object sourced via
            :mod:`carbon_ops.config_loader` utilities.
        carbon_intensity_mapping: Mapping of region identifiers to fallback
            carbon intensities.
        pue_values: Mapping of data-centre profiles to default PUE values.
        default_bucket_minutes: Interpolation bucket size used when no
            configuration override is present.

    Returns:
        A frozen :class:`EstimatorRuntimeConfig` instance encapsulating the
        resolved settings.
    """

    config_region = _extract_config_region(config)
    bucket_minutes = _extract_config_bucket(config, default_bucket_minutes)
    config_pue_default = _extract_config_pue_default(config)

    resolved_region = _resolve_region(region, config_region)
    resolved_intensity = (
        custom_carbon_intensity
        if custom_carbon_intensity is not None
        else carbon_intensity_mapping.get(
            resolved_region,
            carbon_intensity_mapping["global-average"],
        )
    )
    resolved_pue = (
        custom_pue
        if custom_pue is not None
        else _resolve_pue(
            datacenter_type=datacenter_type,
            config_default=config_pue_default,
            pue_values=pue_values,
        )
    )

    provider = intensity_provider or _build_provider_from_config(
        config=config,
        default_mapping=carbon_intensity_mapping,
    )

    missing_policy = _resolve_missing_policy(config)

    return EstimatorRuntimeConfig(
        region=resolved_region,
        datacenter_type=datacenter_type,
        carbon_intensity_gco2_kwh=float(resolved_intensity),
        pue=float(resolved_pue),
        missing_policy=missing_policy,
        bucket_minutes=bucket_minutes,
        intensity_provider=provider,
    )
