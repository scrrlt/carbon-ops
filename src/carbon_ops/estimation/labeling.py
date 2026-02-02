"""Human-readable carbon labeling utilities."""

from __future__ import annotations

from carbon_ops.carbon_models import CarbonEstimate
from carbon_ops.estimation.reporting import (
    compare_carbon_equivalents as reporting_compare,
    derive_rating as reporting_derive,
)

__all__ = [
    "build_carbon_label_payload",
    "compare_carbon_equivalents",
    "derive_rating",
]


def compare_carbon_equivalents(carbon_kgco2: float) -> dict[str, str]:
    """Compatibility wrapper for :mod:`carbon_ops.estimation.reporting`."""

    return reporting_compare(carbon_kgco2)


def derive_rating(carbon_kgco2: float) -> str:
    """Compatibility wrapper for :mod:`carbon_ops.estimation.reporting`."""

    return reporting_derive(carbon_kgco2)


def build_carbon_label_payload(
    *,
    estimate: CarbonEstimate,
    datacenter_type: str,
) -> dict[str, object]:
    """Construct the canonical carbon label payload for a single estimate.

    Args:
        estimate: Canonical carbon estimate for the operation/span.
        datacenter_type: Data-centre profile associated with the estimate.

    Returns:
        Nested dictionary compatible with downstream ledger serializers.
    """

    carbon_kgco2 = estimate.grams / 1000.0
    equivalents = reporting_compare(carbon_kgco2)
    rating = reporting_derive(carbon_kgco2)

    return {
        "carbon_label": {
            "rating": rating,
            "region": estimate.region,
            "datacenter_type": datacenter_type,
            "estimates": estimate.to_dict(),
            "equivalents": equivalents,
            "timestamp": None,
        }
    }
