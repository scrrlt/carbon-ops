"""Tests for CPU and memory telemetry readers with stubbed psutil modules."""

from __future__ import annotations

from dataclasses import dataclass

from carbon_ops.telemetry.cpu import CpuMetricsReader
from carbon_ops.telemetry.memory import MemoryMetricsReader


@dataclass
class FakeCpuFreq:
    """Simple object imitating the psutil cpu_freq return shape."""

    current: float | None


class FakeCpuPsutil:
    """Stub psutil module for CPU tests."""

    def __init__(self, percent: float, freq: float | None) -> None:
        self._percent = percent
        self._freq = freq
        self._primed = False

    def cpu_percent(self, interval: float | None = None) -> float:
        if not self._primed:
            self._primed = True
            return 0.0
        return self._percent

    def cpu_freq(self) -> FakeCpuFreq | None:
        if self._freq is None:
            return None
        return FakeCpuFreq(self._freq)


class FakeMemoryStats:
    """Stub representing psutil virtual memory results."""

    def __init__(self, used: int, percent: float, available: int) -> None:
        self.used = used
        self.percent = percent
        self.available = available


class FakeMemoryPsutil:
    """Stub psutil module for memory tests."""

    def __init__(self, used: int, percent: float, available: int) -> None:
        self._stats = FakeMemoryStats(used, percent, available)

    def virtual_memory(self) -> FakeMemoryStats:
        return self._stats


def test_cpu_metrics_reader_computes_power() -> None:
    """CpuMetricsReader should compute estimated power from utilisation."""
    reader = CpuMetricsReader(psutil_module=FakeCpuPsutil(percent=25.0, freq=2800.0))
    metrics = reader.read()
    assert metrics["cpu_percent"] == 25.0
    assert metrics["cpu_freq_mhz"] == 2800.0
    assert metrics["estimated_power_watts"] > 0.0


def test_cpu_metrics_reader_handles_missing_frequency() -> None:
    """Missing frequency information should default to zero."""
    reader = CpuMetricsReader(psutil_module=FakeCpuPsutil(percent=10.0, freq=None))
    metrics = reader.read()
    assert metrics["cpu_freq_mhz"] == 0.0


def test_memory_metrics_reader_returns_expected_fields() -> None:
    """MemoryMetricsReader should convert bytes to gigabytes."""
    memory_reader = MemoryMetricsReader(
        psutil_module=FakeMemoryPsutil(
            used=4 * 1024**3, percent=50.0, available=8 * 1024**3
        )
    )
    metrics = memory_reader.read()
    assert metrics["memory_used_gb"] == 4.0
    assert metrics["memory_available_gb"] == 8.0
    assert metrics["memory_percent"] == 50.0
