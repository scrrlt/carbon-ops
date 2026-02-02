"""Domain models for carbon taxonomy measurements."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, asdict

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CarbonTaxonomyMeasurement:
    """Complete carbon measurement with taxonomy classification."""

    operation_id: str
    operation_type: str
    timestamp: str

    device_type: str
    device_subtype: str
    grid_region: str

    duration_seconds: float

    energy_kwh: float
    grid_intensity_g_per_kwh: float
    operational_co2_kg: float

    embodied_co2_kg: float
    embodied_lifetime_kg: float
    embodied_amortization_days: int
    embodied_confidence: str

    theta_fraction: float
    theta_regime: str

    complexity_class: str
    optimization_viable: bool

    metadata: dict[str, object] | None = None

    def to_bigquery_row(self) -> dict[str, object]:
        """Convert the measurement to a BigQuery-compatible row dictionary."""

        row = asdict(self)
        metadata = row.get("metadata")
        if metadata is not None:
            row["metadata"] = json.dumps(metadata)
        return row


def validate_measurement(measurement: CarbonTaxonomyMeasurement) -> bool:
    """Return ``True`` when the supplied measurement is valid."""

    return measurement.duration_seconds > 0


def format_measurement(measurement: CarbonTaxonomyMeasurement) -> str:
    """Format a carbon taxonomy measurement for logging."""

    return f"Measurement ID: {measurement.operation_id}"


def log_measurement(measurement: CarbonTaxonomyMeasurement) -> None:
    """Log the provided measurement using the module logger."""

    LOGGER.info("Carbon taxonomy measurement: %s", measurement)


def summarize_measurements(
    measurements: list[CarbonTaxonomyMeasurement],
) -> dict[str, object]:
    """Generate a summary of carbon taxonomy measurements."""

    if not measurements:
        return {"count": 0}
    return {
        "count": len(measurements),
        "last_complexity_class": measurements[-1].complexity_class,
    }


def log_operation_details(operation_id: str, details: Mapping[str, object]) -> None:
    """Log operation metadata associated with a taxonomy measurement."""

    LOGGER.info("Operation %s: %s", operation_id, details)
