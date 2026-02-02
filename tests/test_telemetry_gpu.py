"""Tests for GPU telemetry reader behaviour."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from carbon_ops.telemetry import gpu


@dataclass
class FakeUtilisation:
    gpu: int
    memory: int


@dataclass
class FakeMemoryInfo:
    used: int
    total: int


class FakeNvml:
    """Minimal NVML stub covering the methods used by the reader."""

    def __init__(self, power_mw: int = 50_000, raise_power: bool = False) -> None:
        self._count = 1
        self._power_mw = power_mw
        self._raise_power = raise_power
        self.initialised = False

    def nvmlInit(self) -> None:
        self.initialised = True

    def nvmlShutdown(self) -> None:
        self.initialised = False

    def nvmlDeviceGetCount(self) -> int:
        return self._count

    def nvmlDeviceGetHandleByIndex(self, index: int) -> int:
        return index

    def nvmlDeviceGetUtilizationRates(self, handle: int) -> FakeUtilisation:
        return FakeUtilisation(gpu=40, memory=20)

    def nvmlDeviceGetMemoryInfo(self, handle: int) -> FakeMemoryInfo:
        return FakeMemoryInfo(used=2 * 1024**3, total=8 * 1024**3)

    def nvmlDeviceGetPowerUsage(self, handle: int) -> int:
        if self._raise_power:
            raise RuntimeError("power unavailable")
        return self._power_mw


@pytest.fixture(autouse=True)
def _reset_gpu_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test controls the NVML loader."""

    monkeypatch.setattr(gpu, "load_nvml_library", lambda: None)


def test_gpu_reader_without_nvml_returns_empty() -> None:
    """When NVML is unavailable no GPU metrics should be emitted."""
    reader = gpu.GpuMetricsReader()
    assert reader.read() == []
    reader.shutdown()


def test_gpu_reader_with_nvml_collects_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """GpuMetricsReader should translate NVML structures into dictionaries."""

    monkeypatch.setattr(gpu, "load_nvml_library", lambda: FakeNvml())
    reader = gpu.GpuMetricsReader()
    metrics = reader.read()
    assert metrics
    entry = metrics[0]
    assert entry["power_watts"] == pytest.approx(50.0)
    reader.shutdown()


def test_gpu_reader_handles_power_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Power retrieval failures should fall back to zero."""

    monkeypatch.setattr(gpu, "load_nvml_library", lambda: FakeNvml(raise_power=True))
    reader = gpu.GpuMetricsReader()
    metrics = reader.read()
    assert metrics[0]["power_watts"] == 0.0


def test_gpu_warning_buffer_delivers_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Buffered warnings should flush when a handler is registered."""

    class _FaultyNvml(FakeNvml):
        def nvmlInit(self) -> None:  # type: ignore[override]
            raise RuntimeError("nvml init failed")

    monkeypatch.setattr(gpu, "load_nvml_library", lambda: _FaultyNvml())
    reader = gpu.GpuMetricsReader()
    messages: list[str] = []
    reader.register_warning_handler(messages.append)
    assert any("failed" in message.lower() for message in messages)


def test_gpu_reader_shutdown_without_init() -> None:
    """Shutdown should be safe when NVML was never initialised."""
    reader = gpu.GpuMetricsReader()
    reader.shutdown()
