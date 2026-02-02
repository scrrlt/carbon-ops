"""High-level carbon estimation orchestration."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from carbon_ops.carbon_models import CarbonEstimate, CarbonEstimateDict
from carbon_ops.estimation import defaults as estimation_defaults
from carbon_ops.estimation.configuration import build_runtime_config
from carbon_ops.estimation.engine import EstimationEngine
from carbon_ops.estimation.reporting import (
    compare_carbon_equivalents as reporting_compare_carbon_equivalents,
    derive_rating as reporting_derive_rating,
)
from carbon_ops.intensity_provider import IntensityProvider

if TYPE_CHECKING:
    from carbon_ops.config_loader import CarbonConfig

_MAX_ITERATIONS = 100_000
_MAX_BUCKETS = 10_000


class CarbonEstimator:
    """Estimate carbon emissions from energy telemetry.

    The estimator optionally combines static defaults with dynamic intensity
    providers defined via :class:`~carbon_ops.config_loader.CarbonConfig`.
    """

    MAX_ITERATIONS = _MAX_ITERATIONS
    MAX_BUCKETS = _MAX_BUCKETS

    def __init__(
        self,
        region: str | None = "global-average",
        datacenter_type: str = "cloud-hyperscale",
        *,
        custom_carbon_intensity: float | None = None,
        custom_pue: float | None = None,
        intensity_provider: IntensityProvider | None = None,
        config: "CarbonConfig | None" = None,
    ) -> None:
        """Initialise the estimator with optional overrides.

        Args:
            region: Default geographic region for intensity lookup.
            datacenter_type: Logical data centre category for PUE defaults.
            custom_carbon_intensity: Explicit carbon intensity in gCO2/kWh.
            custom_pue: Explicit PUE value overriding defaults.
            intensity_provider: Pre-configured intensity provider chain.
            config: Optional config object describing providers and defaults.
        """

        self.logger = logging.getLogger("carbon_ops.carbon_estimator")

        estimation_defaults.load_carbon_intensity_mapping.cache_clear()
        estimation_defaults.load_pue_values.cache_clear()
        carbon_map = estimation_defaults.load_carbon_intensity_mapping()
        pue_defaults = estimation_defaults.load_pue_values()

        runtime_config = build_runtime_config(
            region=region,
            datacenter_type=datacenter_type,
            custom_carbon_intensity=custom_carbon_intensity,
            custom_pue=custom_pue,
            intensity_provider=intensity_provider,
            config=config,
            carbon_intensity_mapping=carbon_map,
            pue_values=pue_defaults,
        )

        self.region = runtime_config.region
        self.datacenter_type = runtime_config.datacenter_type
        self._runtime_config = runtime_config
        self._engine = EstimationEngine(
            runtime=runtime_config,
            max_iterations=self.MAX_ITERATIONS,
            max_buckets=self.MAX_BUCKETS,
            logger=self.logger,
        )
        self.carbon_intensity_gco2_kwh = runtime_config.carbon_intensity_gco2_kwh
        self.pue = runtime_config.pue
        self.intensity_provider = runtime_config.intensity_provider
        self.missing_policy_default = runtime_config.missing_policy
        self.bucket_minutes_default = runtime_config.bucket_minutes

        provider_label = (
            type(self.intensity_provider).__name__
            if self.intensity_provider
            else "static"
        )
        self.logger.info(
            "CarbonEstimator initialised",
            extra={
                "region": self.region,
                "carbon_intensity_gco2_kwh": self.carbon_intensity_gco2_kwh,
                "pue": self.pue,
                "provider": provider_label,
            },
        )

    def estimate_from_energy(
        self,
        energy_wh: float,
        *,
        timestamp: datetime | None = None,
        region: str | None = None,
        return_dataclass: bool = False,
    ) -> CarbonEstimate | CarbonEstimateDict:
        """Estimate carbon emissions from an energy reading.

        Args:
            energy_wh: Energy consumption in watt hours.
            timestamp: Optional timestamp aligned with the measurement.
            region: Region override for this estimate.
            return_dataclass: When ``True`` return the dataclass.

        Returns:
            Either a :class:`CarbonEstimate` or a backwards compatible
            ``dict`` representation.
        """

        used_region = region or self.region
        estimate = self._engine.estimate_from_energy(
            energy_wh=energy_wh,
            timestamp=timestamp,
            region=used_region,
        )
        if return_dataclass:
            return estimate
        return estimate.to_dict()

    def estimate_from_power_time(
        self,
        power_watts: float,
        duration_seconds: float,
        *,
        timestamp: datetime | None = None,
        region: str | None = None,
        return_dataclass: bool = False,
    ) -> CarbonEstimate | CarbonEstimateDict:
        """Estimate carbon emissions from uniform power over time.

        Args:
            power_watts: Constant power draw in watts.
            duration_seconds: Duration of the measurement window in seconds.
            timestamp: Optional timestamp representative of the span mid-point.
            region: Optional region override.
            return_dataclass: When ``True`` return the dataclass.

        Returns:
            Either a :class:`CarbonEstimate` or a backwards compatible
            ``dict`` representation.
        """

        energy_wh = (power_watts * duration_seconds) / 3600.0
        return self.estimate_from_energy(
            energy_wh,
            timestamp=timestamp,
            region=region,
            return_dataclass=return_dataclass,
        )

    def estimate_over_span(
        self,
        *,
        start_ts: datetime,
        end_ts: datetime,
        energy_wh: float | None = None,
        power_watts: float | None = None,
        region: str | None = None,
        bucket_minutes: int | None = None,
        missing_policy: str | None = None,
        return_dataclass: bool = False,
        audit_mode: bool = False,
        monte_carlo_iterations: int = 10_000,
        monte_carlo_alpha: float = 0.05,
        monte_carlo_seed: int | None = 42,
    ) -> CarbonEstimate | CarbonEstimateDict:
        """Estimate carbon emissions across a time span with bucketing.

        Args:
            start_ts: Start timestamp of the measured operation.
            end_ts: End timestamp of the measured operation.
            energy_wh: Optional explicit energy budget for the span.
            power_watts: Optional uniform power draw when ``energy_wh`` is unset.
            region: Optional region override for the calculation.
            bucket_minutes: Optional override for bucket duration in minutes.
            missing_policy: Override for missing intensity behaviour.
            return_dataclass: When ``True`` return the dataclass.
            audit_mode: When ``True`` compute Monte Carlo metadata for audit
                submissions instead of the analytical fast path.
            monte_carlo_iterations: Number of Monte Carlo iterations when
                ``audit_mode`` is enabled.
            monte_carlo_alpha: Two-sided significance level for the Monte Carlo
                confidence interval.
            monte_carlo_seed: Optional deterministic seed for Monte Carlo
                simulations.

        Returns:
            Either a :class:`CarbonEstimate` or a backwards compatible
            ``dict`` representation.

        Raises:
            ValueError: If time bounds are invalid, energy inputs are negative,
                or the span would exceed configured bucket limits.
        """

        used_region = region or self.region

        estimate = self._engine.estimate_over_span(
            start_ts=start_ts,
            end_ts=end_ts,
            energy_wh=energy_wh,
            power_watts=power_watts,
            region=used_region,
            bucket_minutes=bucket_minutes,
            missing_policy=missing_policy,
            intensity_reader=self._engine.intensity_reader_for(used_region),
            audit_mode=audit_mode,
            monte_carlo_iterations=monte_carlo_iterations,
            monte_carlo_alpha=monte_carlo_alpha,
            monte_carlo_seed=monte_carlo_seed,
        )

        if return_dataclass:
            return estimate
        return estimate.to_dict()

    def compare_carbon_equivalents(self, carbon_kgco2: float) -> dict[str, str]:
        """Convert carbon emissions into human-friendly equivalents.

        Args:
            carbon_kgco2: Carbon emissions in kilograms of CO2 equivalent.

        Returns:
            Mapping of descriptive equivalence labels to formatted strings.

        Raises:
            ValueError: If ``carbon_kgco2`` is negative.
        """

        return reporting_compare_carbon_equivalents(carbon_kgco2)

    def get_carbon_label(self, energy_wh: float) -> dict[str, object]:
        """Create a descriptive label for the supplied energy usage.

        Args:
            energy_wh: Energy consumption in watt hours.

        Returns:
            Nested dictionary describing the carbon label with equivalents and
            provenance metadata.
        """

        raw_estimate = self.estimate_from_energy(energy_wh, return_dataclass=True)
        if not isinstance(raw_estimate, CarbonEstimate):
            raise TypeError(
                "Expected CarbonEstimate dataclass with return_dataclass=True"
            )

        carbon_kg = raw_estimate.grams / 1000.0
        equivalents = reporting_compare_carbon_equivalents(carbon_kg)
        rating = reporting_derive_rating(carbon_kg)

        return {
            "carbon_label": {
                "rating": rating,
                "region": raw_estimate.region,
                "datacenter_type": self.datacenter_type,
                "estimates": raw_estimate.to_dict(),
                "equivalents": equivalents,
                "timestamp": None,
            }
        }

    @staticmethod
    def get_available_regions() -> dict[str, float]:
        """Return the available region → intensity mapping."""

        estimation_defaults.load_carbon_intensity_mapping.cache_clear()
        return dict(estimation_defaults.load_carbon_intensity_mapping())

    @staticmethod
    def get_available_datacenter_types() -> dict[str, float]:
        """Return the available datacentre type → PUE mapping."""

        estimation_defaults.load_pue_values.cache_clear()
        return dict(estimation_defaults.load_pue_values())

    @property
    def intensity_provider(self) -> IntensityProvider | None:
        """Return the configured intensity provider chain."""

        return self._runtime_config.intensity_provider

    @intensity_provider.setter
    def intensity_provider(self, provider: IntensityProvider | None) -> None:
        """Update the intensity provider and refresh dependent state."""

        self._runtime_config = replace(
            self._runtime_config, intensity_provider=provider
        )
        self._engine = EstimationEngine(
            runtime=self._runtime_config,
            max_iterations=self.MAX_ITERATIONS,
            max_buckets=self.MAX_BUCKETS,
            logger=self.logger,
        )
        self.carbon_intensity_gco2_kwh = self._runtime_config.carbon_intensity_gco2_kwh
        self.pue = self._runtime_config.pue
        self.missing_policy_default = self._runtime_config.missing_policy
        self.bucket_minutes_default = self._runtime_config.bucket_minutes
