"""Core carbon estimation engine and orchestration primitives."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from carbon_ops.monte_carlo import (
    estimate_co2_distribution,
    monte_carlo_summary,
)

from carbon_ops.carbon_models import CarbonEstimate
from carbon_ops.estimation.configuration import EstimatorRuntimeConfig
from carbon_ops.estimation.span import SpanComputationConfig, compute_span_estimate
from carbon_ops.intensity_provider import IntensityReading

_LOGGER = logging.getLogger("carbon_ops.estimation.engine")


def _analytical_meta(estimate: CarbonEstimate) -> dict[str, object]:
    grams = float(estimate.grams)
    sigma = 0.0
    if estimate.uncertainty_pct is not None:
        sigma = grams * (estimate.uncertainty_pct / 100.0)
    lower = max(grams - 2.0 * sigma, 0.0)
    upper = grams + 2.0 * sigma
    return {
        "method": "analytical_truncated",
        "ci_lower_g": lower,
        "ci_upper_g": upper,
        "confidence_level_pct": 95.0,
    }


@dataclass(slots=True)
class EstimationEngine:
    """Orchestrates carbon estimation using a prepared runtime configuration."""

    runtime: EstimatorRuntimeConfig
    max_iterations: int
    max_buckets: int
    logger: logging.Logger = _LOGGER

    def _get_intensity_reading(
        self, timestamp: datetime | None, region: str
    ) -> IntensityReading | None:
        provider = self.runtime.intensity_provider
        if provider is None:
            return None
        try:
            return provider.get_intensity(timestamp, region)
        except (
            OSError,
            ValueError,
            ImportError,
        ) as exc:  # pragma: no cover - defensive
            self.logger.warning("Intensity provider failed", exc_info=exc)
            return None

    def intensity_reader_for(
        self, region: str
    ) -> Callable[[datetime | None], IntensityReading | None]:
        """Return a callable that fetches intensity for the provided region."""

        return lambda timestamp: self._get_intensity_reading(timestamp, region)

    def estimate_from_energy(
        self,
        *,
        energy_wh: float,
        timestamp: datetime | None,
        region: str,
    ) -> CarbonEstimate:
        """Estimate carbon emissions from an energy reading."""

        energy_kwh = energy_wh / 1000.0
        total_energy_kwh = energy_kwh * self.runtime.pue
        reading = self._get_intensity_reading(timestamp, region)
        intensity = (
            reading.intensity_gco2_kwh
            if reading is not None
            else self.runtime.carbon_intensity_gco2_kwh
        )
        carbon_grams = total_energy_kwh * intensity

        estimate = CarbonEstimate(
            grams=float(carbon_grams),
            intensity_g_per_kwh=float(intensity),
            energy_kwh=float(energy_kwh),
            total_energy_with_pue_kwh=float(total_energy_kwh),
            pue_used=float(self.runtime.pue),
            source=(reading.provider_version or "static") if reading else "static",
            region=region,
            start_ts=timestamp,
            end_ts=timestamp,
            uncertainty_pct=reading.uncertainty if reading else None,
            provider_version=reading.provider_version if reading else None,
            calibration_version=reading.calibration_version if reading else None,
            conversion_version=reading.conversion_version if reading else None,
            quality_flag="measured" if reading else "estimated",
        )
        estimate.meta = _analytical_meta(estimate)
        return estimate

    def estimate_over_span(
        self,
        *,
        start_ts: datetime,
        end_ts: datetime,
        intensity_reader: Callable[[datetime | None], IntensityReading | None],
        energy_wh: float | None,
        power_watts: float | None,
        region: str,
        bucket_minutes: int | None,
        missing_policy: str | None,
        audit_mode: bool = False,
        monte_carlo_iterations: int = 10_000,
        monte_carlo_alpha: float = 0.05,
        monte_carlo_seed: int | None = 42,
    ) -> CarbonEstimate:
        """Estimate carbon emissions across a span.

        Args:
            start_ts: Beginning of the interval.
            end_ts: End of the interval.
            intensity_reader: Callback returning intensity readings.
            energy_wh: Observed energy in watt-hours for the span, if any.
            power_watts: Observed instantaneous power in watts for the span.
            region: Grid region identifier.
            bucket_minutes: Optional override for bucket size in minutes.
            missing_policy: Handling strategy for missing intensity data.
            audit_mode: When ``True``, run a Monte Carlo simulation to populate
                metadata suitable for audit-grade reporting.
            monte_carlo_iterations: Number of Monte Carlo draws when
                ``audit_mode`` is enabled.
            monte_carlo_alpha: Two-sided significance level for Monte Carlo
                confidence intervals.
            monte_carlo_seed: Optional deterministic seed for Monte Carlo
                runs.
        """

        config = SpanComputationConfig(
            pue=self.runtime.pue,
            default_intensity=float(self.runtime.carbon_intensity_gco2_kwh),
            max_iterations=self.max_iterations,
            max_buckets=self.max_buckets,
            bucket_minutes_default=self.runtime.bucket_minutes,
            missing_policy_default=self.runtime.missing_policy,
            source_label=(
                type(self.runtime.intensity_provider).__name__
                if self.runtime.intensity_provider is not None
                else "static"
            ),
        )

        estimate = compute_span_estimate(
            start_ts=start_ts,
            end_ts=end_ts,
            energy_wh=energy_wh,
            power_watts=power_watts,
            region=region,
            bucket_minutes=bucket_minutes,
            missing_policy=missing_policy,
            config=config,
            intensity_reader=intensity_reader,
        )
        if audit_mode:
            duration_seconds = max((end_ts - start_ts).total_seconds(), 0.0)
            if duration_seconds > 0:
                if power_watts is not None:
                    start_power = end_power = float(power_watts)
                else:
                    span_energy_wh = (
                        float(energy_wh)
                        if energy_wh is not None
                        else estimate.energy_kwh * 1000.0
                    )
                    start_power = end_power = (
                        span_energy_wh * 3600.0 / duration_seconds
                        if span_energy_wh > 0
                        else 0.0
                    )

                intensity_sigma = 0.0
                if estimate.uncertainty_pct is not None:
                    intensity_sigma = estimate.intensity_g_per_kwh * (
                        estimate.uncertainty_pct / 100.0
                    )

                samples = estimate_co2_distribution(
                    duration_s=duration_seconds,
                    start_power_w=start_power,
                    end_power_w=end_power,
                    n=max(1, monte_carlo_iterations),
                    idle_baseline_w_mu=0.0,
                    idle_baseline_w_sigma=0.0,
                    power_residual_sigma_w=0.0,
                    pue_mu=self.runtime.pue,
                    pue_sigma=0.0,
                    intensity_gco2_kwh_mu=estimate.intensity_g_per_kwh,
                    intensity_gco2_kwh_sigma=intensity_sigma,
                    seed=monte_carlo_seed,
                )
                summary_meta = monte_carlo_summary(
                    samples,
                    alpha=monte_carlo_alpha,
                    iters=max(1, monte_carlo_iterations),
                    seed=monte_carlo_seed,
                )
                estimate.meta = {key: value for key, value in summary_meta.items()}
            else:
                estimate.meta = _analytical_meta(estimate)
        else:
            estimate.meta = _analytical_meta(estimate)
        return estimate
