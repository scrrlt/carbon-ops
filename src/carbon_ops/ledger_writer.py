"""Helpers to serialize and append carbon estimates to an audit ledger."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .carbon_models import CarbonEstimate, CarbonEstimateDict
from .schemas import AuditRecord, CURRENT_AUDIT_SCHEMA_VERSION
from .tools.ledger import append_signed_entry
from .tools.verify import SIGNATURE_FIELDS, Signer

RESERVED_EXTRA_KEYS = set(SIGNATURE_FIELDS) | {"prev_hash"}


def _to_float(value: object, *, default: float) -> float:
    """Best-effort float conversion with a fallback default."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _to_optional_float(value: object | None) -> float | None:
    """Return ``None`` or a float parsed from ``value``."""
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


def _legacy_dict_to_event(data: dict[str, object]) -> dict[str, object]:
    """Translate legacy dict outputs into the audit event structure."""
    region = str(data.get("region", "unknown"))
    source = str(data.get("source", "static"))
    grams = _to_float(data.get("carbon_emissions_gco2", 0.0), default=0.0)
    energy_kwh = _to_float(data.get("energy_consumed_kwh", 0.0), default=0.0)
    pue_used = _to_float(data.get("pue_used", 1.2), default=1.2)
    total_energy_with_pue_kwh = _to_float(
        data.get("total_energy_with_pue_kwh", energy_kwh * pue_used),
        default=energy_kwh * pue_used,
    )
    intensity = _to_float(data.get("carbon_intensity_used_gco2_kwh", 0.0), default=0.0)
    uncertainty = _to_optional_float(data.get("intensity_uncertainty"))
    quality_flag = str(data.get("quality_flag", "fallback"))
    meta = data.get("meta")
    return {
        "type": "carbon_estimate",
        "region": region,
        "source": source,
        "grams": grams,
        "energy_kwh": energy_kwh,
        "total_energy_with_pue_kwh": total_energy_with_pue_kwh,
        "pue_used": pue_used,
        "intensity_g_per_kwh": intensity,
        "uncertainty_pct": uncertainty,
        "quality_flag": quality_flag,
        "start_ts": data.get("start_ts"),
        "end_ts": data.get("end_ts"),
        "provider_version": data.get("provider_version"),
        "calibration_version": data.get("calibration_version"),
        "conversion_version": data.get("conversion_version"),
        "coverage_pct": data.get("coverage_pct"),
        "datacenter_type": data.get("datacenter_type"),
        "labels": data.get("labels"),
        "meta": meta if isinstance(meta, dict) else None,
    }


def _estimate_to_event_payload(
    estimate: CarbonEstimate | CarbonEstimateDict | dict[str, object],
) -> dict[str, object]:
    """Return the raw event payload prior to schema validation."""
    if isinstance(estimate, CarbonEstimate):
        base = estimate.to_ndjson_event()
    else:
        base = _legacy_dict_to_event(dict(estimate))
    payload = {
        "kind": "carbon_ops",
        "schema_version": CURRENT_AUDIT_SCHEMA_VERSION,
        **base,
    }
    return payload


def carbon_event_from_estimate(
    estimate: CarbonEstimate | CarbonEstimateDict | dict[str, object],
    extra: dict[str, object] | None = None,
) -> AuditRecord:
    """Build a validated audit record from an estimate payload.

    Args:
        estimate: Canonical :class:`CarbonEstimate` or the legacy dict payload
            produced by older integrations.
        extra: Optional metadata constrained to the audit schema fields
            (for example ``{"labels": {"env": "prod"}}``).

    Returns:
        A fully validated :class:`AuditRecord` instance ready for signing.

    Raises:
        ValueError: If ``extra`` attempts to override reserved signature fields.
        RuntimeError: If the constructed payload violates :class:`AuditRecord`.
    """

    payload = _estimate_to_event_payload(estimate)
    if extra:
        for key, value in extra.items():
            if key in RESERVED_EXTRA_KEYS:
                raise ValueError(
                    f"Field '{key}' cannot be overridden via extra metadata."
                )
            payload[key] = value

    try:
        return AuditRecord.model_validate(payload)
    except ValidationError as exc:  # pragma: no cover - rewrapped for clarity
        raise RuntimeError(
            "Audit integrity failure: payload violates the AuditRecord schema."
        ) from exc


def append_carbon_estimate(
    ledger_path: str | Path,
    estimate: CarbonEstimate | CarbonEstimateDict | dict[str, object],
    signer: Signer,
    *,
    extra: dict[str, object] | None = None,
    include_prev_hash: bool = True,
) -> dict[str, object]:
    """Append a signed carbon estimate event to the ledger.

    Args:
        ledger_path: Destination NDJSON ledger path.
        estimate: Canonical estimate dataclass or legacy dict payload.
        signer: Ed25519 signer used to produce the audit signature.
        extra: Optional schema-compliant metadata to enrich the record.
        include_prev_hash: When ``True`` the record links to the previous entry.

    Returns:
        The signed JSON envelope written to ``ledger_path``.
    """
    ledger_p = Path(ledger_path)
    record = carbon_event_from_estimate(estimate, extra=extra)
    payload = record.model_dump_json_ready()
    return append_signed_entry(
        ledger_p, payload, signer, include_prev_hash=include_prev_hash
    )
