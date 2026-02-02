"""Carbon taxonomy logger orchestrating operational and embodied emissions."""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from types import ModuleType
from typing import Deque, Protocol, cast, runtime_checkable

from carbon_ops.carbon_taxonomy.calculations import (
    THETA_MARGINAL_THRESHOLD,
    calculate_operational_emissions,
    compute_theta_fraction,
    get_theta_regime,
)
from carbon_ops.carbon_taxonomy.models import CarbonTaxonomyMeasurement
from carbon_ops.research.embodied_carbon_db import calculate_embodied_for_operation
from carbon_ops.settings import CarbonOpsSettings, get_settings

LOGGER = logging.getLogger(__name__)

BIGQUERY_AVAILABLE = False
bigquery_module: ModuleType | None = None

try:  # pragma: no cover - optional dependency
    from google.cloud import bigquery as _runtime_bigquery
except Exception:  # pragma: no cover - optional dependency
    _runtime_bigquery = None
else:
    bigquery_module = _runtime_bigquery
    BIGQUERY_AVAILABLE = True

FALLBACK_EMBODIED_CARBON_KG_DEFAULT: float = 42.0


@runtime_checkable
class _BigQueryDataset(Protocol):
    def table(self, table_id: str) -> object:
        """Return a table reference."""


@runtime_checkable
class _BigQueryClient(Protocol):
    def dataset(self, dataset_id: str) -> _BigQueryDataset:
        """Return a dataset reference."""

    def insert_rows_json(
        self, table: object, json_rows: list[dict[str, object]]
    ) -> list[object]:
        """Insert JSON rows into the supplied table."""


@dataclass(frozen=True)
class EmbodiedCarbonEstimate:
    """Canonical representation of embodied carbon details."""

    embodied_kg: float
    total_lifetime_kg: float
    amortization_days: int
    confidence: str


def get_fallback_embodied_carbon_kg(
    settings: CarbonOpsSettings | None = None,
) -> float:
    """Return the fallback embodied carbon value with optional override."""

    settings_obj = settings or get_settings()
    override = settings_obj.fallback_embodied_carbon_kg
    if override is not None:
        LOGGER.info(
            "Using configured fallback embodied carbon override: %s kg CO₂e",
            override,
        )
        return override
    return FALLBACK_EMBODIED_CARBON_KG_DEFAULT


class CarbonTaxonomyLogger:
    """Logger that tracks both operational and embodied carbon."""

    def __init__(
        self,
        device_type: str = "cloud_vm",
        device_subtype: str = "cpu_only",
        grid_region: str = "US_AVERAGE",
        bigquery_table: str | None = None,
        gcp_project: str | None = None,
        history_limit: int = 10_000,
        *,
        settings: CarbonOpsSettings | None = None,
    ) -> None:
        """Initialise the taxonomy logger.

        Args:
            device_type: Logical device category used for embodied lookups.
            device_subtype: Specific device variant within ``device_type``.
            grid_region: Region key for grid intensity defaults.
            bigquery_table: Optional ``dataset.table`` identifier for exports.
            gcp_project: Optional Google Cloud project for BigQuery.
            history_limit: Maximum number of retained measurements.
            settings: Precomputed settings instance used for overrides.
        """

        self.device_type = device_type
        self.device_subtype = device_subtype
        self.grid_region = grid_region
        self.bigquery_table = bigquery_table
        self.gcp_project = gcp_project
        self._settings: CarbonOpsSettings = settings or get_settings()

        self.measurements: Deque[CarbonTaxonomyMeasurement] = deque(
            maxlen=history_limit
        )
        self._bq_client: _BigQueryClient | None = None
        if BIGQUERY_AVAILABLE and bigquery_table and bigquery_module is not None:
            try:
                client = cast(
                    _BigQueryClient,
                    bigquery_module.Client(project=gcp_project),
                )
                self._bq_client = client
            except Exception:  # pragma: no cover - defensive
                LOGGER.warning(
                    "Failed to instantiate BigQuery client",
                    exc_info=True,
                )

    @property
    def bq_client(self) -> _BigQueryClient | None:
        """Expose the configured BigQuery client for compatibility."""

        return self._bq_client

    @bq_client.setter
    def bq_client(self, client: _BigQueryClient | None) -> None:
        """Allow tests to inject a BigQuery client double."""

        self._bq_client = client

    @contextmanager
    def track_operation(
        self,
        operation_type: str,
        operation_id: str,
        metadata: Mapping[str, object] | None = None,
    ) -> Generator[None, None, None]:
        """Context manager that records a carbon taxonomy measurement."""

        start = perf_counter()
        try:
            yield
        finally:
            duration = perf_counter() - start
            measurement = self._build_measurement(
                operation_type=operation_type,
                operation_id=operation_id,
                duration_seconds=duration,
                metadata=metadata,
            )
            self.measurements.append(measurement)
            self._log_to_bigquery(measurement)

    def export_to_json(self, filepath: str | Path) -> None:
        """Export collected measurements to a JSON file."""

        path = Path(filepath)
        payload = [asdict(measurement) for measurement in self.measurements]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_taxonomy_summary(self) -> dict[str, object]:
        """Return summary statistics for collected measurements."""

        if not self.measurements:
            return {"error": "No measurements collected"}
        thetas = [m.theta_fraction for m in self.measurements]
        operational = [m.operational_co2_kg for m in self.measurements]
        embodied = [m.embodied_co2_kg for m in self.measurements]
        viable = sum(1 for m in self.measurements if m.optimization_viable)
        total_measurements = len(self.measurements)
        return {
            "measurement_count": total_measurements,
            "avg_theta": sum(thetas) / total_measurements,
            "min_theta": min(thetas),
            "max_theta": max(thetas),
            "total_operational_kg": sum(operational),
            "total_embodied_kg": sum(embodied),
            "dominant_class": self.measurements[-1].complexity_class,
            "optimization_viable_pct": (viable / total_measurements) * 100.0,
        }

    def _build_measurement(
        self,
        *,
        operation_type: str,
        operation_id: str,
        duration_seconds: float,
        metadata: Mapping[str, object] | None,
    ) -> CarbonTaxonomyMeasurement:
        """Construct a measurement instance for the completed operation."""

        energy_kwh = self._estimate_energy(duration_seconds)
        grid_intensity = self._resolve_grid_intensity()
        operational_co2_kg = calculate_operational_emissions(energy_kwh, grid_intensity)

        embodied_estimate = self._resolve_embodied_estimate(duration_seconds)
        theta = compute_theta_fraction(
            operational_co2_kg, embodied_estimate.embodied_kg
        )
        complexity_class = self._classify_complexity(theta)
        metadata_dict = dict(metadata) if metadata is not None else None

        return CarbonTaxonomyMeasurement(
            operation_id=operation_id,
            operation_type=operation_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            device_type=self.device_type,
            device_subtype=self.device_subtype,
            grid_region=self.grid_region,
            duration_seconds=duration_seconds,
            energy_kwh=energy_kwh,
            grid_intensity_g_per_kwh=grid_intensity,
            operational_co2_kg=operational_co2_kg,
            embodied_co2_kg=embodied_estimate.embodied_kg,
            embodied_lifetime_kg=embodied_estimate.total_lifetime_kg,
            embodied_amortization_days=embodied_estimate.amortization_days,
            embodied_confidence=embodied_estimate.confidence,
            theta_fraction=theta,
            theta_regime=get_theta_regime(theta),
            complexity_class=complexity_class,
            optimization_viable=theta < THETA_MARGINAL_THRESHOLD,
            metadata=metadata_dict,
        )

    def _resolve_embodied_estimate(
        self, duration_seconds: float
    ) -> EmbodiedCarbonEstimate:
        """Resolve embodied carbon details for the current operation."""

        try:
            raw = calculate_embodied_for_operation(
                device_type=self.device_type,
                device_subtype=self.device_subtype,
                duration_seconds=duration_seconds,
            )
        except Exception:  # pragma: no cover - defensive
            raw = {}

        if isinstance(raw, Mapping):
            embodied_value = raw.get("embodied_kg")
            lifetime_value = raw.get("total_lifetime_kg")
            amortization_value = raw.get("amortization_days")
            confidence_value = raw.get("confidence")
        else:
            embodied_value = None
            lifetime_value = None
            amortization_value = None
            confidence_value = None

        if (
            isinstance(embodied_value, (int, float))
            and isinstance(lifetime_value, (int, float))
            and isinstance(amortization_value, (int, float))
            and isinstance(confidence_value, str)
        ):
            return EmbodiedCarbonEstimate(
                embodied_kg=float(embodied_value),
                total_lifetime_kg=float(lifetime_value),
                amortization_days=int(amortization_value),
                confidence=confidence_value,
            )

        fallback_value = get_fallback_embodied_carbon_kg(self._settings)
        LOGGER.warning(
            "Embodied carbon calculation failed for %s/%s; using fallback %.2f kg",
            self.device_type,
            self.device_subtype,
            fallback_value,
        )
        return EmbodiedCarbonEstimate(
            embodied_kg=fallback_value,
            total_lifetime_kg=1_000.0,
            amortization_days=365,
            confidence="fallback",
        )

    def _estimate_energy(self, duration_seconds: float) -> float:
        """Estimate energy consumption in kilowatt hours."""

        return self._resolve_power_kw() * (duration_seconds / 3600.0)

    def _resolve_power_kw(self) -> float:
        """Resolve configured power draw in kilowatts."""

        device_map = POWER_ESTIMATES.get(self.device_type, {})
        return float(device_map.get(self.device_subtype, 0.1))

    def _resolve_grid_intensity(self) -> float:
        """Resolve grid intensity in grams CO₂ per kilowatt hour."""

        return float(GRID_INTENSITIES.get(self.grid_region, 400.0))

    def _classify_complexity(self, theta: float) -> str:
        """Classify the operational complexity using the theta fraction."""

        if theta < 0.15:
            return "C-P[operational-dominated]"
        if theta < 0.30:
            return "C-P[marginal]"
        return "C-NP[embodied-dominated]"

    def _log_to_bigquery(self, measurement: CarbonTaxonomyMeasurement) -> None:
        """Push the measurement to BigQuery when configured."""

        if self._bq_client is None or not self.bigquery_table:
            return
        try:
            dataset_name, table_name = self.bigquery_table.split(".")
            table_ref = self._bq_client.dataset(dataset_name).table(table_name)
            errors = self._bq_client.insert_rows_json(
                table_ref, [measurement.to_bigquery_row()]
            )
            if errors:
                LOGGER.error("BigQuery insert errors: %s", errors)
        except Exception:  # pragma: no cover - defensive
            LOGGER.error("BigQuery logging failed", exc_info=True)


def _load_json_resource(name: str) -> dict[str, object]:
    """Load a JSON resource from the packaged data directory."""

    try:
        import importlib.resources as resources

        data = (
            resources.files("carbon_ops.data")
            .joinpath(name)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return {}

    try:
        loaded = json.loads(data)
    except json.JSONDecodeError:
        return {}

    if not isinstance(loaded, dict):
        return {}

    normalized: dict[str, object] = {}
    for key, value in loaded.items():
        if isinstance(key, str):
            normalized[key] = value
    return normalized


def _build_power_estimates() -> dict[str, dict[str, float]]:
    """Build power estimate mapping from packaged resources."""

    payload = _load_json_resource("power_estimates.json")
    estimates: dict[str, dict[str, float]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        sub_mapping: dict[str, float] = {}
        for sub_key, sub_value in value.items():
            if not isinstance(sub_key, str):
                continue
            if isinstance(sub_value, (int, float, str)):
                try:
                    sub_mapping[sub_key] = float(sub_value)
                except ValueError:
                    continue
        if sub_mapping:
            estimates[key] = sub_mapping
    return estimates or _POWER_DEFAULTS


def _build_grid_intensities() -> dict[str, float]:
    """Build grid intensity mapping from packaged resources."""

    payload = _load_json_resource("grid_intensity.json")
    intensities: dict[str, float] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, (int, float, str)):
            try:
                intensities[key] = float(value)
            except ValueError:
                continue
    return intensities or _GRID_DEFAULTS


_POWER_DEFAULTS: dict[str, dict[str, float]] = {
    "cloud_vm": {"cpu_only": 0.15, "gpu_t4": 0.35},
    "edge": {"nvidia_jetson_nano": 0.01, "raspberry_pi_4": 0.007},
    "mobile": {"smartphone_flagship": 0.003},
    "iot": {"sensor_node_battery": 0.0001},
}

_GRID_DEFAULTS: dict[str, float] = {
    "US_AVERAGE": 385.0,
    "GCP_US_CENTRAL1": 420.0,
    "UK": 220.0,
}

POWER_ESTIMATES: dict[str, dict[str, float]] = _build_power_estimates()
GRID_INTENSITIES: dict[str, float] = _build_grid_intensities()
