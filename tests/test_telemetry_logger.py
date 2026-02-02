"""Unit tests for telemetry energy logger internals."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from carbon_ops.telemetry.cpu import CpuMetricsReader
from carbon_ops.telemetry.gpu import GpuMetricsReader
from carbon_ops.telemetry.logger import EnergyLogger
from carbon_ops.telemetry.memory import MemoryMetricsReader
from carbon_ops.telemetry.rapl import RaplReader


class FixedCpuReader:
    """Deterministic CPU reader for testing."""

    def __init__(self, watts: float) -> None:
        self._watts = watts

    def read(self) -> dict[str, float]:
        return {
            "cpu_percent": 50.0,
            "cpu_freq_mhz": 2400.0,
            "estimated_power_watts": self._watts,
        }


class FixedMemoryReader:
    """Deterministic memory reader for testing."""

    def read(self) -> dict[str, float]:
        return {
            "memory_used_gb": 4.0,
            "memory_percent": 40.0,
            "memory_available_gb": 12.0,
        }


class FixedGpuReader:
    """GPU reader with configurable metrics."""

    def __init__(self, power: float) -> None:
        self._power = power
        self.gpu_count = 1

    def register_warning_handler(self, handler: Callable[[str], None]) -> None:
        handler("GPU monitoring enabled via stub")

    def read(self) -> list[dict[str, float]]:
        return [
            {
                "gpu_id": 0,
                "gpu_utilization_percent": 20.0,
                "memory_utilization_percent": 30.0,
                "memory_used_gb": 2.0,
                "memory_total_gb": 8.0,
                "power_watts": self._power,
            }
        ]

    def shutdown(self) -> None:
        return


class RecordingRaplReader:
    """RAPL reader returning predefined energy counters."""

    def __init__(self, values: list[float]) -> None:
        self._values = values
        self._index = 0

    @property
    def is_available(self) -> bool:
        return True

    def read_total_energy_uj(self) -> float:
        value = self._values[self._index]
        self._index = min(self._index + 1, len(self._values) - 1)
        return value


class DisabledRaplReader:
    """Rapl reader stub when capability is unavailable."""

    is_available = False

    def read_total_energy_uj(self) -> float:  # pragma: no cover - not invoked
        return 0.0


def build_logger(
    cpu_watts: float, gpu_watts: float, rapl_reader: object
) -> EnergyLogger:
    """Construct an ``EnergyLogger`` with deterministic telemetry readers."""

    logger = EnergyLogger(log_level=logging.CRITICAL)
    logger.cpu_reader = cast(CpuMetricsReader, FixedCpuReader(cpu_watts))
    logger.memory_reader = cast(MemoryMetricsReader, FixedMemoryReader())
    logger.gpu_reader = cast(GpuMetricsReader, FixedGpuReader(gpu_watts))
    logger.rapl_reader = cast(RaplReader, rapl_reader)
    return logger


def test_monitor_with_rapl(tmp_path: Path) -> None:
    """Energy monitor should annotate metrics with RAPL data when available."""
    logger = build_logger(90.0, 20.0, RecordingRaplReader([1_000_000.0, 1_500_000.0]))

    with logger.monitor("rapl_case"):
        pass

    end_metric = logger.metrics[-1]
    assert "energy" in end_metric
    assert end_metric["energy"] is not None
    energy = cast(dict[str, object], end_metric["energy"])
    assert cast(float, energy["energy_wh_total"]) > 0.0
    assert energy["calibration_version"] == logger.calibration_version

    export_path = tmp_path / "metrics.json"
    logger.export_metrics(export_path)
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_measurements"] >= 2


def test_compute_summary_without_rapl() -> None:
    """Active energy should exclude idle baseline when RAPL is unavailable."""
    logger = build_logger(60.0, 10.0, DisabledRaplReader())
    logger.idle_baseline_watts = 50.0

    with logger.monitor("no_rapl"):
        pass

    end_metric = logger.metrics[-1]
    assert end_metric["energy"] is not None
    energy = cast(dict[str, object], end_metric["energy"])
    assert cast(float, energy["energy_wh_total"]) >= 0.0
    assert cast(float, energy["energy_wh_active"]) >= 0.0


def test_get_metrics_summary_empty() -> None:
    """Summary should indicate when no metrics are collected."""
    logger = build_logger(30.0, 5.0, DisabledRaplReader())

    summary = logger.get_metrics_summary()
    assert summary["message"] == "No metrics collected yet"

    logger.log_metrics("sample")
    populated = logger.get_metrics_summary()
    assert populated["total_measurements"] == 1
    assert populated["gpu_monitoring_enabled"] is True


@pytest.mark.asyncio
async def test_logger_async_helpers() -> None:
    """Async helper methods and compatibility properties should function."""

    logger = build_logger(40.0, 5.0, DisabledRaplReader())

    result = await logger.log_metrics_async("async_op")
    assert result["operation"] == "async_op"

    baseline = await logger.calibrate_idle_async(samples=1, interval=0.0)
    assert baseline is not None

    logger.gpu_available = False
    assert logger.gpu_count == 0
    logger.gpu_count = 2
    assert logger.gpu_count == 2
    assert logger.rapl_available is False

    cpu_metrics = logger.get_cpu_metrics()
    memory_metrics = logger.get_memory_metrics()
    gpu_metrics = logger.get_gpu_metrics()

    assert cpu_metrics["estimated_power_watts"] >= 0.0
    assert memory_metrics["memory_percent"] >= 0.0
    assert isinstance(gpu_metrics, list)
