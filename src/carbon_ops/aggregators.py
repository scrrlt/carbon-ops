"""Aggregation helpers for :mod:`carbon_ops` carbon estimates.

The utilities in this module favour strict typing, deterministic aggregation,
and predictable output shapes so that downstream compliance tooling can perform
schema validation without bespoke adapters.
"""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import Iterable, TypedDict

from carbon_ops.carbon_models import CarbonEstimate

__all__ = ["AggregatedMetrics", "aggregate_estimates"]


class AggregatedMetrics(TypedDict):
    """Schema for grouped carbon metrics."""

    count: int
    total_grams: float
    total_energy_kwh: float
    total_energy_with_pue_kwh: float
    intensity_energy_weighted: float
    pue_energy_weighted: float
    relative_uncertainty_pct: float


def _energy_weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float:
    """Return the energy-weighted mean for ``values``.

    Args:
        values: Sequence of intensity-like measurements.
        weights: Energy weights aligned with ``values``.

    Returns:
        Weighted mean scaled by the supplied energy weights. Returns ``0.0``
        when the denominator is zero to preserve deterministic behaviour.
    """

    numerator = 0.0
    denominator = 0.0
    for value, weight in zip(values, weights):
        denominator += weight
        numerator += value * weight
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def _rss_relative_uncertainty(
    grams: Iterable[float],
    uncertainties_pct: Iterable[float | None],
) -> float:
    """Combine relative uncertainties using the root-sum-square method.

    Args:
        grams: Carbon mass per estimate expressed in grams.
        uncertainties_pct: Relative uncertainties (percent, 0-100) aligned with
            ``grams``.

    Returns:
        Combined uncertainty in percent. Missing values are ignored in the RSS
        calculation; if every bucket is missing uncertainty the result is 0.0.
    """

    sigma_squared_sum = 0.0
    total_grams = 0.0
    for gram_value, uncertainty in zip(grams, uncertainties_pct):
        total_grams += gram_value
        if uncertainty is None:
            continue
        sigma = gram_value * (uncertainty / 100.0)
        sigma_squared_sum += sigma * sigma
    if total_grams <= 0.0:
        return 0.0
    return (sqrt(sigma_squared_sum) / total_grams) * 100.0


def aggregate_estimates(
    estimates: Iterable[CarbonEstimate],
    *,
    by: str | None = None,
) -> dict[str, AggregatedMetrics]:
    """Aggregate a collection of ``CarbonEstimate`` instances.

    Args:
        estimates: Carbon estimate stream to aggregate.
        by: Optional grouping key. Supported values are ``"region"`` and
            ``"source"``. Omit or pass ``"all"`` to aggregate across a single
            bucket.

    Returns:
        Mapping of group key to :class:`AggregatedMetrics` summary payloads. The
        mapping is empty when ``estimates`` is empty.
    """

    if by not in {None, "all", "region", "source"}:
        raise ValueError(
            "Parameter 'by' must be one of None, 'all', 'region', 'source'."
        )

    grouping = "all" if by in (None, "all") else by
    buckets: dict[str, list[CarbonEstimate]] = defaultdict(list)

    for estimate in estimates:
        key = "all"
        if grouping == "region":
            key = estimate.region
        elif grouping == "source":
            key = estimate.source
        buckets[key].append(estimate)

    summaries: dict[str, AggregatedMetrics] = {}
    for key, items in buckets.items():
        grams_values = [float(item.grams) for item in items]
        energy_values = [float(item.energy_kwh) for item in items]
        total_energy = sum(energy_values)
        total_energy_with_pue = sum(
            float(item.total_energy_with_pue_kwh) for item in items
        )

        intensity_weighted = (
            _energy_weighted_mean(
                (float(item.intensity_g_per_kwh) for item in items),
                energy_values,
            )
            if total_energy > 0.0
            else 0.0
        )
        pue_weighted = (
            _energy_weighted_mean(
                (float(item.pue_used) for item in items),
                energy_values,
            )
            if total_energy > 0.0
            else 0.0
        )
        rel_uncertainty = _rss_relative_uncertainty(
            grams_values, (item.uncertainty_pct for item in items)
        )

        summaries[key] = AggregatedMetrics(
            count=len(items),
            total_grams=sum(grams_values),
            total_energy_kwh=total_energy,
            total_energy_with_pue_kwh=total_energy_with_pue,
            intensity_energy_weighted=intensity_weighted,
            pue_energy_weighted=pue_weighted,
            relative_uncertainty_pct=rel_uncertainty,
        )
    return summaries
