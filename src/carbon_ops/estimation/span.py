"""Span estimation helpers for :mod:`carbon_ops`.

The functions in this module are intentionally pure and stateless so that
higher-level orchestrators can reuse the logic without inheriting large
monolithic classes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from carbon_ops.carbon_models import CarbonEstimate
from carbon_ops.intensity_provider import IntensityReading

SpanIntensityReader = Callable[[datetime], IntensityReading | None]


@dataclass(frozen=True)
class SpanComputationConfig:
    """Configuration container for span carbon estimation.

    Attributes:
        pue: Power usage effectiveness multiplier applied to energy.
        default_intensity: Static fallback intensity in gCO2/kWh.
        max_iterations: Hard cap on bucket iterations to prevent infinite loops.
        max_buckets: Maximum bucket count derived from span length.
        bucket_minutes_default: Default bucket duration in minutes.
        missing_policy_default: Strategy for handling missing intensity reads.
        source_label: Human-readable label for the intensity data source.
    """

    pue: float
    default_intensity: float
    max_iterations: int
    max_buckets: int
    bucket_minutes_default: int
    missing_policy_default: str
    source_label: str


@dataclass(frozen=True)
class _BucketResult:
    energy_kwh: float
    energy_with_pue_kwh: float
    carbon_grams: float
    energy_fraction: float
    uncertainty_fraction: float | None


def compute_span_estimate(
    *,
    start_ts: datetime,
    end_ts: datetime,
    energy_wh: float | None,
    power_watts: float | None,
    region: str,
    bucket_minutes: int | None,
    missing_policy: str | None,
    config: SpanComputationConfig,
    intensity_reader: SpanIntensityReader,
) -> CarbonEstimate:
    """Compute a span-based carbon estimate.

    Args:
        start_ts: Start timestamp of the measured operation.
        end_ts: End timestamp of the measured operation.
        energy_wh: Total energy consumption in watt hours across the span.
        power_watts: Optional uniform power draw when ``energy_wh`` is absent.
        region: Region identifier used for intensity lookups.
        bucket_minutes: Optional override for bucket duration in minutes.
        missing_policy: Override for handling missing intensity readings.
        config: Immutable configuration controlling span behaviour.
        intensity_reader: Callable resolving intensity readings for timestamps.

    Returns:
        A :class:`CarbonEstimate` representing the span aggregation.

    Raises:
        ValueError: If timestamps are inverted, invalid energy parameters are
            provided, or the span would exceed configured bucket limits.
    """
    if end_ts <= start_ts:
        raise ValueError("end_ts must be > start_ts")

    duration_seconds = (end_ts - start_ts).total_seconds()
    if energy_wh is None and power_watts is None:
        raise ValueError("Provide energy_wh or power_watts")
    if energy_wh is not None and energy_wh < 0:
        raise ValueError("energy_wh must be >= 0")
    if power_watts is not None and power_watts < 0:
        raise ValueError("power_watts must be >= 0")

    if energy_wh is not None:
        actual_energy_wh = float(energy_wh)
    else:
        if power_watts is None:
            raise ValueError("power_watts must be provided when energy_wh is None")
        actual_energy_wh = (float(power_watts) * duration_seconds) / 3600.0
    energy_kwh_total = actual_energy_wh / 1000.0

    bucket_minutes_value = (
        bucket_minutes if bucket_minutes is not None else config.bucket_minutes_default
    )
    bucket_minutes_value = int(bucket_minutes_value)
    if bucket_minutes_value < 1:
        raise ValueError("bucket_minutes must be >= 1")

    estimated_buckets = (duration_seconds / 60.0) / bucket_minutes_value
    if estimated_buckets > config.max_buckets:
        raise ValueError(
            "Requested span exceeds bucket limit; increase bucket_minutes or reduce the time range."
        )

    bucket_delta = timedelta(minutes=bucket_minutes_value)
    missing_policy_value = (missing_policy or config.missing_policy_default).lower()

    bucket_results: list[_BucketResult] = []
    processed_energy_kwh = 0.0

    current = start_ts
    iteration_count = 0

    while current < end_ts:
        if iteration_count > config.max_iterations:
            recommended = max(
                1, math.ceil(duration_seconds / 60.0 / config.max_buckets)
            )
            raise ValueError(
                "Too many buckets in estimate_over_span. Increase bucket_minutes to at least %s for this span."
                % recommended
            )
        iteration_count += 1

        bucket_end = min(current + bucket_delta, end_ts)
        seconds = (bucket_end - current).total_seconds()
        fraction = seconds / duration_seconds
        bucket_energy_kwh = energy_kwh_total * fraction
        bucket_energy_with_pue = bucket_energy_kwh * config.pue

        reading = intensity_reader(current)
        if reading is None:
            result = _handle_missing_reading(
                policy=missing_policy_value,
                results=bucket_results,
                default_intensity=config.default_intensity,
            )
            if result is None:
                current = bucket_end
                continue
            intensity, uncertainty_fraction = result
        else:
            intensity = float(reading.intensity_gco2_kwh)
            uncertainty_fraction = (
                reading.uncertainty / 100.0 if reading.uncertainty is not None else None
            )

        carbon_grams = bucket_energy_with_pue * intensity
        bucket_results.append(
            _BucketResult(
                energy_kwh=bucket_energy_kwh,
                energy_with_pue_kwh=bucket_energy_with_pue,
                carbon_grams=carbon_grams,
                energy_fraction=fraction,
                uncertainty_fraction=uncertainty_fraction,
            )
        )
        processed_energy_kwh += bucket_energy_kwh
        current = bucket_end

    total_carbon = math.fsum(result.carbon_grams for result in bucket_results)
    energy_with_pue_total = math.fsum(
        result.energy_with_pue_kwh for result in bucket_results
    )

    aggregate_uncertainty = _combine_uncertainty(bucket_results)
    aggregate_intensity = (
        (total_carbon / energy_with_pue_total)
        if energy_with_pue_total > 0
        else float(config.default_intensity)
    )
    coverage_pct = (
        processed_energy_kwh / energy_kwh_total if energy_kwh_total > 0 else 1.0
    )

    return CarbonEstimate(
        grams=float(total_carbon),
        intensity_g_per_kwh=float(aggregate_intensity),
        energy_kwh=float(processed_energy_kwh),
        total_energy_with_pue_kwh=float(energy_with_pue_total),
        pue_used=float(config.pue),
        source=config.source_label,
        region=region,
        start_ts=start_ts,
        end_ts=end_ts,
        uncertainty_pct=aggregate_uncertainty,
        provider_version=None,
        calibration_version=None,
        conversion_version=None,
        quality_flag="estimated",
        coverage_pct=coverage_pct,
    )


def _handle_missing_reading(
    *,
    policy: str,
    results: list[_BucketResult],
    default_intensity: float,
) -> tuple[float, float | None] | None:
    if policy == "drop":
        return None
    if results:
        last = results[-1]
        if last.energy_with_pue_kwh <= 0:
            return float(default_intensity), last.uncertainty_fraction
        intensity = last.carbon_grams / last.energy_with_pue_kwh
        return float(intensity), last.uncertainty_fraction
    return float(default_intensity), None


def _combine_uncertainty(buckets: list[_BucketResult]) -> float | None:
    rss_terms: list[float] = []
    has_uncertainty = False
    for bucket in buckets:
        if bucket.uncertainty_fraction is None:
            continue
        has_uncertainty = True
        rss_terms.append((bucket.energy_fraction * bucket.uncertainty_fraction) ** 2)
    if not has_uncertainty:
        return None
    return math.sqrt(sum(rss_terms)) * 100.0
