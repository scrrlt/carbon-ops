"""Pydantic models describing public carbon-ops schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SchemaVersionLiteral = Literal["0.1.0"]
CURRENT_AUDIT_SCHEMA_VERSION: SchemaVersionLiteral = "0.1.0"


class AuditRecord(BaseModel):
    """Immutable, versioned schema for a carbon audit ledger entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["carbon_ops"] = Field(
        default="carbon_ops",
        description="Canonical namespace for carbon-ops audit records.",
    )
    schema_version: SchemaVersionLiteral = Field(
        default=CURRENT_AUDIT_SCHEMA_VERSION,
        description="Semantic version of the audit record schema.",
    )
    type: Literal["carbon_estimate"] = Field(
        default="carbon_estimate",
        description="Event type identifier within the carbon namespace.",
    )

    region: str = Field(
        ...,
        description="Grid region identifier (for example, 'us-west').",
        min_length=1,
    )
    source: str = Field(
        ...,
        description="Data provenance label (provider chain entry).",
        min_length=1,
    )
    provider_version: str | None = Field(
        default=None,
        description="Version string reported by the intensity provider.",
    )
    calibration_version: str | None = Field(
        default=None,
        description="Identifier for the calibration workflow applied to telemetry.",
    )
    conversion_version: str | None = Field(
        default=None,
        description="Identifier for the unit conversion strategy used.",
    )
    datacenter_type: str | None = Field(
        default=None,
        description="Logical data centre classification associated with the workload.",
    )
    labels: dict[str, str] | None = Field(
        default=None,
        description="Optional key/value metadata propagated with the ledger entry.",
    )

    grams: float = Field(
        ...,
        ge=0.0,
        description="Carbon emissions in grams of CO2e.",
    )
    energy_kwh: float = Field(
        ...,
        ge=0.0,
        description="Measured energy consumption in kilowatt hours.",
    )
    total_energy_with_pue_kwh: float = Field(
        ...,
        ge=0.0,
        description="Energy consumption including PUE adjustments (kWh).",
    )
    pue_used: float = Field(
        ...,
        ge=0.0,
        description="Effective power usage effectiveness applied to the estimate.",
    )
    intensity_g_per_kwh: float = Field(
        ...,
        ge=0.0,
        description="Grid carbon intensity used for the estimate (gCO2/kWh).",
    )
    uncertainty_pct: float | None = Field(
        default=None,
        ge=0.0,
        description="Uncertainty expressed as a percentage of total emissions.",
    )
    quality_flag: Literal["measured", "estimated", "fallback"] = Field(
        ...,
        description="Quality descriptor for the estimate inputs.",
    )
    coverage_pct: float | None = Field(
        default=None,
        ge=0.0,
        description="Percentage of the intended time span successfully covered.",
    )
    meta: dict[str, object] | None = Field(
        default=None,
        description=(
            "Auxiliary metadata associated with the estimate (for example, "
            "estimation method tags or confidence interval details)."
        ),
    )

    start_ts: datetime | None = Field(
        default=None,
        description="Start timestamp of the measurement window (UTC).",
    )
    end_ts: datetime | None = Field(
        default=None,
        description="End timestamp of the measurement window (UTC).",
    )

    prev_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of the previous canonical ledger payload.",
        min_length=1,
    )

    def model_dump_json_ready(self) -> dict[str, object]:
        """Return a JSON-serialisable payload with ``None`` values removed."""

        return self.model_dump(mode="json", exclude_none=True)
