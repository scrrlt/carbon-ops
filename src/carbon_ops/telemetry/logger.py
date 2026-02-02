"""High-level energy logger composed from telemetry readers."""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import math
import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, cast
from uuid import uuid4

import psutil

from carbon_ops.governor.client import (
    GovernorClient,
    GovernorSnapshot,
    GovernorUnavailableError,
)
from carbon_ops.settings import CarbonOpsSettings, get_settings
from carbon_ops.types import CPUMetrics, EnergyMetric, GPUMetrics, MemoryMetrics
from carbon_ops.telemetry.cpu import CpuMetricsReader
from carbon_ops.telemetry.gpu import GpuMetricsReader
from carbon_ops.telemetry.logging_pipeline import (
    configure_structured_logging,
    shutdown_listeners,
)
from carbon_ops.telemetry.memory import MemoryMetricsReader
from carbon_ops.telemetry.rapl import RaplReader

MODULE_LOGGER = logging.getLogger("carbon_ops.telemetry.lifecycle")


@dataclass(slots=True)
class _CpuTimesSample:
    """Snapshot of process and system CPU times in seconds."""

    process_seconds: float
    total_seconds: float


@dataclass(slots=True)
class EnergyLogger:
    """Collect and persist energy telemetry for operations.

    The logger orchestrates CPU, GPU, memory, and optional RAPL readers while
    emitting structured JSON logs. Environment-driven defaults are supplied via
    :class:`CarbonOpsSettings` to honour the security requirement that
    configuration must flow through pydantic-based settings.

    Attributes:
        log_level: Logging verbosity applied to the structured logger.
        history_limit: Maximum number of telemetry entries retained in memory.
        trace_id: Correlation identifier propagated to structured logs.
        cpu_reader: CPU metrics reader dependency.
        gpu_reader: GPU metrics reader dependency.
        rapl_reader: Optional RAPL reader for precise CPU energy counters.
        memory_reader: Memory metrics reader dependency.
        settings: Environment-backed settings override.
    """

    log_level: int = logging.INFO
    history_limit: int = 10_000
    trace_id: str | None = None
    cpu_reader: CpuMetricsReader = field(default_factory=CpuMetricsReader)
    gpu_reader: GpuMetricsReader = field(
        default_factory=lambda: GpuMetricsReader(), repr=False
    )
    rapl_reader: RaplReader = field(default_factory=RaplReader, repr=False)
    memory_reader: MemoryMetricsReader = field(
        default_factory=MemoryMetricsReader, repr=False
    )
    settings: CarbonOpsSettings | None = field(default=None, repr=False)
    governor_client: GovernorClient | None = field(default=None, repr=False)
    logger: logging.Logger = field(init=False, repr=False)
    _listener: logging.handlers.QueueListener = field(init=False, repr=False)
    metrics: list[EnergyMetric] = field(init=False, repr=False)
    idle_baseline_watts: float | None = field(init=False)
    calibration_version: str = field(init=False)
    _log_listener: logging.handlers.QueueListener = field(init=False, repr=False)
    process: psutil.Process | None = field(init=False, repr=False)
    _governor_error_logged: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        settings_obj = self.settings or get_settings()
        self.settings = settings_obj
        if self.trace_id is None:
            self.trace_id = str(uuid4())

        self.logger = logging.getLogger("carbon_ops.energy")
        self._listener = configure_structured_logging(
            self.logger, trace_id=self.trace_id, level=self.log_level
        )
        self._log_listener = self._listener

        def warning_handler(message: str) -> None:
            self.logger.warning(message)

        if hasattr(self.gpu_reader, "register_warning_handler"):
            register_handler = cast(
                Callable[[Callable[[str], None]], None],
                getattr(self.gpu_reader, "register_warning_handler"),
            )
            register_handler(warning_handler)
        else:
            self.gpu_reader.on_warning = warning_handler

        try:
            self.process = psutil.Process()
        except psutil.Error as exc:  # pragma: no cover - platform dependent
            self.logger.warning(
                "Failed to initialize process handle for CPU attribution",
                extra={"error": str(exc)},
            )
            self.process = None
        if self.governor_client is None:
            self.governor_client = self._build_governor_client(settings_obj)
        self._governor_error_logged = False

        self.metrics = []
        self.idle_baseline_watts = settings_obj.idle_baseline_watts
        self.calibration_version = settings_obj.calibration_version

    def log_metrics(
        self, operation: str, additional_info: Mapping[str, object] | None = None
    ) -> EnergyMetric:
        """Collect a single telemetry sample.

        Args:
            operation: Logical operation name being monitored.
            additional_info: Optional metadata merged into the metrics record.

        Returns:
            The telemetry record stored in the in-memory history buffer.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        cpu_metrics: CPUMetrics = self.cpu_reader.read()
        memory_metrics: MemoryMetrics = self.memory_reader.read()
        gpu_metrics: list[GPUMetrics] = self.gpu_reader.read()

        total_power = float(cpu_metrics["estimated_power_watts"]) + sum(
            gpu_metric.get("power_watts", 0.0) or 0.0 for gpu_metric in gpu_metrics
        )

        metric: EnergyMetric = {
            "timestamp": timestamp,
            "operation": operation,
            "cpu": cpu_metrics,
            "memory": memory_metrics,
            "gpu": gpu_metrics,
            "total_estimated_power_watts": total_power,
            "additional_info": dict(additional_info) if additional_info else None,
        }

        self.metrics.append(metric)
        if len(self.metrics) > self.history_limit:
            del self.metrics[0]

        self.logger.info(
            "Telemetry sample collected",
            extra={
                "operation": operation,
                "total_power_watts": total_power,
                "cpu_percent": cpu_metrics["cpu_percent"],
                "memory_percent": memory_metrics["memory_percent"],
            },
        )

        return metric

    def _build_governor_client(
        self, settings: CarbonOpsSettings
    ) -> GovernorClient | None:
        """Create a governor client from settings when platform support exists."""
        socket_path = (
            Path(settings.governor_socket_path)
            if settings.governor_socket_path
            else None
        )
        try:
            return GovernorClient(
                socket_path=socket_path,
                timeout=settings.governor_request_timeout,
            )
        except GovernorUnavailableError:
            self.logger.debug("Governor client unavailable", exc_info=True)
            return None

    def _take_governor_snapshot(self) -> GovernorSnapshot | None:
        """Return a governor snapshot or ``None`` when IPC is unavailable."""
        client = self.governor_client
        if client is None:
            return None
        try:
            return client.snapshot()
        except GovernorUnavailableError as exc:
            if not self._governor_error_logged:
                self.logger.warning(
                    "Governor unavailable; switching to monitor-only mode",
                    extra={"error": str(exc)},
                )
                self._governor_error_logged = True
            self.governor_client = None
            return None

    def _sample_cpu_times(self) -> _CpuTimesSample | None:
        """Capture process and system CPU time deltas for attribution."""
        try:
            if self.process is None:
                return None
            proc_times = self.process.cpu_times()
            system_times = psutil.cpu_times()
        except (psutil.Error, OSError) as exc:  # pragma: no cover - system dependent
            self.logger.debug("Failed to sample CPU times", exc_info=exc)
            return None
        return _CpuTimesSample(
            process_seconds=float(sum(proc_times)),
            total_seconds=float(sum(system_times)),
        )

    async def log_metrics_async(
        self, operation: str, additional_info: Mapping[str, object] | None = None
    ) -> EnergyMetric:
        """Collect telemetry without blocking the event loop.

        Args:
            operation: Logical operation name being monitored.
            additional_info: Optional metadata merged into the metrics record.

        Returns:
            The telemetry record stored in the in-memory history buffer.
        """
        return await asyncio.to_thread(self.log_metrics, operation, additional_info)

    @property
    def gpu_available(self) -> bool:
        """Return whether GPU monitoring is currently enabled."""
        return self.gpu_reader.gpu_count > 0

    @gpu_available.setter
    def gpu_available(self, value: bool) -> None:
        if not value:
            self.gpu_reader.gpu_count = 0

    @property
    def gpu_count(self) -> int:
        """Return the detected GPU device count."""
        return self.gpu_reader.gpu_count

    @gpu_count.setter
    def gpu_count(self, value: int) -> None:
        self.gpu_reader.gpu_count = max(0, int(value))

    @property
    def rapl_available(self) -> bool:
        """Return whether RAPL counters are available on the host."""
        return self.rapl_reader.is_available

    def get_cpu_metrics(self) -> CPUMetrics:
        """Return the latest CPU metrics snapshot."""
        return self.cpu_reader.read()

    def get_memory_metrics(self) -> MemoryMetrics:
        """Return the latest memory metrics snapshot."""
        return self.memory_reader.read()

    def get_gpu_metrics(self) -> list[GPUMetrics]:
        """Return the latest GPU metrics snapshot."""
        return self.gpu_reader.read()

    def calibrate_idle(self, samples: int = 5, interval: float = 0.2) -> float | None:
        """Measure and persist an idle baseline power reading.

        Args:
            samples: Number of samples collected for the baseline.
            interval: Delay between samples in seconds.

        Returns:
            The computed idle baseline in watts when successful, otherwise
            ``None`` if sampling failed.
        """
        readings: list[float] = []
        for _ in range(max(1, samples)):
            cpu_metrics = self.cpu_reader.read()
            gpu_metrics = self.gpu_reader.read()
            sample_power = cpu_metrics["estimated_power_watts"] + sum(
                metric.get("power_watts", 0.0) or 0.0 for metric in gpu_metrics
            )
            readings.append(sample_power)
            time.sleep(max(0.0, interval))

        if not readings:
            return None

        baseline = sum(readings) / len(readings)
        self.idle_baseline_watts = baseline
        self.logger.info(
            "Idle baseline calibrated",
            extra={
                "idle_baseline_watts": baseline,
                "calibration_version": self.calibration_version,
            },
        )
        return baseline

    async def calibrate_idle_async(
        self, samples: int = 5, interval: float = 0.2
    ) -> float | None:
        """Measure the idle baseline without blocking the event loop."""
        return await asyncio.to_thread(self.calibrate_idle, samples, interval)

    @contextmanager
    def monitor(
        self, operation: str, log_interval: float | None = None
    ) -> Generator[EnergyMetric, None, None]:
        """Measure power usage over the lifetime of a context.

        Args:
            operation: Logical operation name being monitored.
            log_interval: Reserved for future periodic sampling support.

        Yields:
            The metrics captured at the start of the monitored block.
        """
        _ = log_interval  # Reserved for future interval-based sampling
        start_monotonic = time.perf_counter()
        governor_start = self._take_governor_snapshot()
        cpu_sample_start = self._sample_cpu_times()
        if self.rapl_reader.is_available:
            start_rapl = self.rapl_reader.read_total_energy_uj()
        else:
            start_rapl = math.nan
        start_metrics = self.log_metrics(f"{operation}_start")

        try:
            yield start_metrics
        finally:
            end_monotonic = time.perf_counter()
            duration_seconds = end_monotonic - start_monotonic
            end_metrics = self.log_metrics(
                f"{operation}_end",
                {"duration_seconds": duration_seconds},
            )

            governor_end = self._take_governor_snapshot()
            cpu_sample_end = self._sample_cpu_times()

            energy_summary = self._compute_energy_summary(
                duration_seconds,
                start_metrics,
                end_metrics,
                start_rapl,
                governor_start,
                governor_end,
                cpu_sample_start,
                cpu_sample_end,
            )
            end_metrics["energy"] = energy_summary

            self.logger.info(
                "Operation completed",
                extra={
                    "operation": operation,
                    "duration_seconds": duration_seconds,
                    "energy_wh_total": energy_summary["energy_wh_total"],
                    "energy_wh_active": energy_summary["energy_wh_active"],
                    "allocation_ratio": energy_summary.get("allocation_ratio"),
                    "attribution_mode": energy_summary.get("attribution_mode"),
                },
            )

    def _compute_energy_summary(
        self,
        duration_seconds: float,
        start_metrics: EnergyMetric,
        end_metrics: EnergyMetric,
        start_rapl_uj: float,
        governor_start: GovernorSnapshot | None,
        governor_end: GovernorSnapshot | None,
        cpu_times_start: _CpuTimesSample | None,
        cpu_times_end: _CpuTimesSample | None,
    ) -> dict[str, object]:
        """Compute energy summary metrics for the monitored span.

        Args:
            duration_seconds: Duration of the monitored operation in seconds.
            start_metrics: Metrics captured at the start of the operation.
            end_metrics: Metrics captured at the end of the operation.
            start_rapl_uj: Initial RAPL reading in microjoules.
            governor_start: Governor snapshot captured at context entry.
            governor_end: Governor snapshot captured at context exit.
            cpu_times_start: CPU time sample at context entry.
            cpu_times_end: CPU time sample at context exit.

        Returns:
            Summary dictionary suitable for inclusion in the metrics stream.
        """
        duration_hours = duration_seconds / 3600.0 if duration_seconds > 0 else 0.0
        gpu_energy_wh = self._estimate_gpu_energy_wh(
            duration_seconds, start_metrics, end_metrics
        )

        allocation_ratio: float | None = None
        attribution_mode = "monitor_only"
        avg_power = 0.0
        energy_wh_total = 0.0
        cpu_energy_wh: float | None = None

        if (
            duration_seconds > 0
            and governor_start is not None
            and governor_end is not None
        ):
            delta_uj = governor_end.total_energy_uj - governor_start.total_energy_uj
            if delta_uj >= 0:
                cpu_energy_wh = delta_uj / 3_600_000_000.0
                energy_wh_total = max(cpu_energy_wh + gpu_energy_wh, 0.0)
                if duration_hours > 0:
                    avg_power = energy_wh_total / duration_hours

                if cpu_times_start is not None and cpu_times_end is not None:
                    proc_delta = (
                        cpu_times_end.process_seconds - cpu_times_start.process_seconds
                    )
                    total_delta = (
                        cpu_times_end.total_seconds - cpu_times_start.total_seconds
                    )
                    if total_delta > 0 and proc_delta >= 0:
                        # Clamp to [0.0, 1.0] because OS CPU accounting can drift: per-process
                        # times occasionally exceed aggregated system time due to rounding,
                        # multicore sampling skew, or heterogeneous clocks.
                        allocation_ratio = max(0.0, min(proc_delta / total_delta, 1.0))
                attribution_mode = (
                    "governor_cpu_time"
                    if allocation_ratio is not None
                    else "governor_energy"
                )

        if cpu_energy_wh is None:
            rapl_available = self.rapl_reader.is_available
            end_rapl_uj = (
                self.rapl_reader.read_total_energy_uj() if rapl_available else math.nan
            )
            if (
                duration_seconds > 0
                and rapl_available
                and not (math.isnan(start_rapl_uj) or math.isnan(end_rapl_uj))
            ):
                rapl_delta = end_rapl_uj - start_rapl_uj
                if rapl_delta >= 0:
                    cpu_energy_wh = rapl_delta / 3_600_000_000.0
                    energy_wh_total = max(cpu_energy_wh + gpu_energy_wh, 0.0)
                    if duration_hours > 0:
                        avg_power = energy_wh_total / duration_hours
            if cpu_energy_wh is None:
                avg_power = (
                    self._total_estimated_power(start_metrics)
                    + self._total_estimated_power(end_metrics)
                ) / 2.0
                if duration_hours > 0:
                    energy_wh_total = avg_power * duration_hours
            attribution_mode = "monitor_only"

        idle = self.idle_baseline_watts
        active_avg_power = max(avg_power - (idle or 0.0), 0.0)
        energy_wh_active = (
            active_avg_power * duration_hours if duration_hours > 0 else 0.0
        )

        summary = {
            "duration_seconds": float(duration_seconds),
            "avg_power_watts": float(avg_power),
            "idle_baseline_watts": idle,
            "calibration_version": self.calibration_version,
            "energy_wh_total": float(energy_wh_total),
            "energy_wh_active": float(energy_wh_active),
            "allocation_ratio": allocation_ratio,
            "attribution_mode": attribution_mode,
        }
        if cpu_energy_wh is not None:
            summary["cpu_energy_wh"] = float(cpu_energy_wh)
        summary["gpu_energy_wh"] = float(gpu_energy_wh)
        return cast(dict[str, object], summary)

    def _estimate_gpu_energy_wh(
        self,
        duration_seconds: float,
        start_metrics: EnergyMetric,
        end_metrics: EnergyMetric,
    ) -> float:
        if duration_seconds <= 0:
            return 0.0
        gpu_start_power = self._gpu_power_watts(start_metrics)
        gpu_end_power = self._gpu_power_watts(end_metrics)
        gpu_avg_power = (gpu_start_power + gpu_end_power) / 2.0
        return (gpu_avg_power * duration_seconds) / 3600.0

    def _gpu_power_watts(self, metric: EnergyMetric) -> float:
        """Compute aggregate GPU power in watts for a metrics record."""
        if "gpu" not in metric:
            return 0.0
        return float(sum(item.get("power_watts", 0.0) or 0.0 for item in metric["gpu"]))

    def _total_estimated_power(self, metric: EnergyMetric) -> float:
        """Return the total estimated power in watts for a metrics record."""
        if "total_estimated_power_watts" not in metric:
            return 0.0
        return float(metric["total_estimated_power_watts"])

    def get_metrics_summary(self) -> dict[str, float | int | bool | str]:
        """Summarise the collected metrics buffer.

        Returns:
            Aggregate statistics describing the metrics history.
        """
        if not self.metrics:
            return {"message": "No metrics collected yet"}

        total_measurements = len(self.metrics)
        cpu_values = [
            metric["cpu"]["cpu_percent"] for metric in self.metrics if "cpu" in metric
        ]
        memory_values = [
            metric["memory"]["memory_percent"]
            for metric in self.metrics
            if "memory" in metric
        ]
        power_values = [
            metric["total_estimated_power_watts"]
            for metric in self.metrics
            if "total_estimated_power_watts" in metric
        ]

        avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else 0.0
        avg_memory = sum(memory_values) / len(memory_values) if memory_values else 0.0
        avg_power = sum(power_values) / len(power_values) if power_values else 0.0

        return {
            "total_measurements": total_measurements,
            "average_cpu_percent": avg_cpu,
            "average_memory_percent": avg_memory,
            "average_power_watts": avg_power,
            "gpu_monitoring_enabled": self.gpu_reader.gpu_count > 0,
        }

    def export_metrics(self, filepath: str | Path) -> None:
        """Persist collected metrics to a JSON file.

        Args:
            filepath: Destination path for the emitted JSON payload.
        """
        payload = {
            "summary": self.get_metrics_summary(),
            "metrics": list(self.metrics),
        }
        target_path = Path(filepath)
        target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.logger.info("Metrics exported", extra={"path": str(target_path)})

    def __del__(self) -> None:  # pragma: no cover - gc semantics are non-deterministic
        listener = getattr(self, "_listener", None)
        if listener is not None:
            try:
                shutdown_listeners([listener])
            except Exception as exc:  # pragma: no cover - destructor safety
                MODULE_LOGGER.debug(
                    "Suppressed listener shutdown exception during GC",
                    exc_info=exc,
                )
        gpu_reader = getattr(self, "gpu_reader", None)
        if gpu_reader is not None:
            try:
                gpu_reader.shutdown()
            except Exception as exc:  # pragma: no cover - destructor safety
                MODULE_LOGGER.debug(
                    "Suppressed GPU shutdown exception during GC",
                    exc_info=exc,
                )
