"""Carbon-related data models for the carbon-ops toolkit.

Phase 1 introduces a CarbonEstimate dataclass that can be returned by
CarbonEstimator methods while preserving backward compatibility via
:meth:`CarbonEstimate.to_dict`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict


class CarbonEstimateDict(TypedDict):
    """Legacy dictionary schema for backward compatibility."""

    energy_consumed_wh: float
    energy_consumed_kwh: float
    total_energy_with_pue_kwh: float
    carbon_emissions_gco2: float
    carbon_emissions_kgco2: float
    carbon_emissions_tonnes: float
    carbon_intensity_used_gco2_kwh: float
    intensity_uncertainty: float | None
    provider_version: str | None
    pue_used: float
    meta: dict[str, object] | None


@dataclass
class CarbonEstimate:
    """
    Canonical carbon estimate for a single operation/span.

    Fields align with the refactor proposal (v1.0) and existing dict outputs.
    Use .to_dict() for backward compatibility with current tests/consumers.
    """

    # Core values
    grams: float
    intensity_g_per_kwh: float
    energy_kwh: float
    total_energy_with_pue_kwh: float
    pue_used: float

    # Provenance/context
    source: str
    region: str
    start_ts: datetime | None = None
    end_ts: datetime | None = None

    # Uncertainty & provider metadata
    uncertainty_pct: float | None = None
    provider_version: str | None = None
    calibration_version: str | None = None
    conversion_version: str | None = None

    # Quality indicator
    quality_flag: str = "measured"  # "measured", "estimated", "fallback"

    # Coverage for dropped buckets
    coverage_pct: float | None = None
    meta: dict[str, object] | None = None

    def to_dict(self) -> CarbonEstimateDict:
        """Return the legacy dict shape expected by existing callers/tests."""
        carbon_gco2 = float(self.grams)
        carbon_kgco2 = carbon_gco2 / 1000.0
        carbon_tonnes = carbon_kgco2 / 1000.0
        energy_kwh = float(self.energy_kwh)
        energy_wh = energy_kwh * 1000.0

        return {
            "energy_consumed_wh": energy_wh,
            "energy_consumed_kwh": energy_kwh,
            "total_energy_with_pue_kwh": float(self.total_energy_with_pue_kwh),
            "carbon_emissions_gco2": carbon_gco2,
            "carbon_emissions_kgco2": carbon_kgco2,
            "carbon_emissions_tonnes": carbon_tonnes,
            "carbon_intensity_used_gco2_kwh": float(self.intensity_g_per_kwh),
            "intensity_uncertainty": self.uncertainty_pct,
            "provider_version": self.provider_version,
            "pue_used": float(self.pue_used),
            "meta": self.meta,
        }

    def to_ndjson_event(self) -> dict[str, object]:
        """Minimal NDJSON-ready event (ledger writer can sign/chain later)."""
        return {
            "type": "carbon_estimate",
            "region": self.region,
            "source": self.source,
            "start_ts": self.start_ts.isoformat() if self.start_ts else None,
            "end_ts": self.end_ts.isoformat() if self.end_ts else None,
            "grams": float(self.grams),
            "intensity_g_per_kwh": float(self.intensity_g_per_kwh),
            "energy_kwh": float(self.energy_kwh),
            "total_energy_with_pue_kwh": float(self.total_energy_with_pue_kwh),
            "pue_used": float(self.pue_used),
            "uncertainty_pct": self.uncertainty_pct,
            "provider_version": self.provider_version,
            "calibration_version": self.calibration_version,
            "conversion_version": self.conversion_version,
            "quality_flag": self.quality_flag,
            "coverage_pct": self.coverage_pct,
            "meta": self.meta,
        }
