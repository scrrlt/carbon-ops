"""Tests for energy logger monitoring functionality."""

import importlib
import sys
import time
import types

import pytest

from carbon_ops import energy_logger as el_mod
import carbon_ops.telemetry.logger as telemetry_logger
from carbon_ops.governor.client import GovernorSnapshot
from carbon_ops.telemetry.logger import _CpuTimesSample


class _Freq:
    def __init__(self, current: float):
        self.current = current


class _VM:
    def __init__(self, used, percent, available):
        self.used = used
        self.percent = percent
        self.available = available


class FakeNVML:
    """Mock NVML for testing GPU functionality."""

    def nvmlInit(self):
        """Initialize NVML."""
        return None

    def nvmlDeviceGetCount(self):
        """Get device count."""
        return 1

    def nvmlDeviceGetHandleByIndex(self, i):
        """Get device handle."""
        return object()

    def nvmlDeviceGetUtilizationRates(self, handle):
        """Get utilization rates."""

        class U:
            gpu = 10
            memory = 20

        return U()

    def nvmlDeviceGetMemoryInfo(self, handle):
        """Get memory info."""

        class M:
            used = 1 * 1024**3
            total = 4 * 1024**3

        return M()

    def nvmlDeviceGetPowerUsage(self, handle):
        """Get power usage."""
        return 50000

    def nvmlShutdown(self):
        """Shutdown NVML."""
        return None


def test_gpu_metrics_and_monitor(monkeypatch, tmp_path):
    """Test GPU metrics and monitoring."""
    # Patch psutil functions used by EnergyLogger
    monkeypatch.setattr(el_mod.psutil, "cpu_percent", lambda interval=0.1: 50.0)
    monkeypatch.setattr(el_mod.psutil, "cpu_freq", lambda: _Freq(2400.0))
    monkeypatch.setattr(
        el_mod.psutil,
        "virtual_memory",
        lambda: _VM(used=2 * 1024**3, percent=40.0, available=3 * 1024**3),
    )

    # Inject fake pynvml as a module and reload energy_logger so it picks it up
    fake = types.ModuleType("pynvml")
    fake.nvmlInit = lambda: None
    fake.nvmlDeviceGetCount = lambda: 1
    fake.nvmlDeviceGetHandleByIndex = lambda i: object()

    class _U(dict):
        def __init__(self):
            super().__init__(gpu=10, memory=20)

    def _util(handle):
        return _U()

    fake.nvmlDeviceGetUtilizationRates = _util

    class _M(dict):
        def __init__(self):
            super().__init__(used=1 * 1024**3, total=4 * 1024**3)

    fake.nvmlDeviceGetMemoryInfo = lambda h: _M()
    fake.nvmlDeviceGetPowerUsage = lambda h: 50000
    fake.nvmlShutdown = lambda: None

    monkeypatch.setitem(sys.modules, "pynvml", fake)

    # Reload module to pick up fake pynvml import
    el = importlib.reload(importlib.import_module("carbon_ops.energy_logger"))

    # Patch psutil functions used by the new module
    monkeypatch.setattr(el.psutil, "cpu_percent", lambda interval=0.1: 50.0)
    monkeypatch.setattr(el.psutil, "cpu_freq", lambda: _Freq(2400.0))
    monkeypatch.setattr(
        el.psutil,
        "virtual_memory",
        lambda: _VM(used=2 * 1024**3, percent=40.0, available=3 * 1024**3),
    )

    logger = el.EnergyLogger()
    assert logger.gpu_available
    g = logger.get_gpu_metrics()
    assert isinstance(g, list) and len(g) == 1
    assert g[0]["power_watts"] == 50.0

    # Use monitor context to generate start/end metrics
    with logger.monitor("test_op"):
        time.sleep(0.01)

    # Validate last metric (end) contains energy summary
    last = logger.metrics[-1]
    assert "energy" in last
    assert last["energy"]["energy_wh_total"] >= 0.0
    assert "allocation_ratio" in last["energy"]
    assert "attribution_mode" in last["energy"]


def test_gpu_init_failure(monkeypatch, caplog):
    """Test GPU initialization failure."""

    # Use a clean helper function
    def fail_nvml_init():
        raise RuntimeError("nvml init failed")

    bad = types.ModuleType("pynvml")
    bad.nvmlInit = fail_nvml_init
    monkeypatch.setitem(sys.modules, "pynvml", bad)

    # Reload module so it picks up the failing nvml
    el = importlib.reload(importlib.import_module("carbon_ops.energy_logger"))
    logger = el.EnergyLogger()
    assert not logger.gpu_available
    assert "GPU monitoring unavailable" in caplog.text


def test_log_metrics_with_additional_info():
    """Test logging metrics with additional information."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    additional_info = {"model": "gpt-3", "batch_size": 32}
    metric = logger.log_metrics("ai_inference", additional_info)

    assert metric["additional_info"] == additional_info
    assert metric["operation"] == "ai_inference"


def test_monitor_context_manager_with_exception():
    """Test that monitor context manager handles exceptions properly."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    with pytest.raises(RuntimeError, match="Simulated error"):
        with logger.monitor("failing_operation"):
            raise RuntimeError("Simulated error")

    # Should still have logged the start metric (and end metric due to exception)
    assert len(logger.metrics) == 2
    assert logger.metrics[0]["operation"] == "failing_operation_start"


def test_calibrate_idle_success():
    """Test idle calibration success."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    baseline = logger.calibrate_idle(samples=3, interval=0.01)
    assert baseline is not None
    assert baseline > 0
    assert logger.idle_baseline_watts == baseline


def test_calibrate_idle_failure():
    """Test idle calibration failure handling."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    # This should not crash even if calibration fails
    baseline = logger.calibrate_idle(samples=1, interval=0.001)
    # May return None if calibration fails, but shouldn't crash
    assert baseline is None or isinstance(baseline, float)


def test_energy_logger_without_gpu():
    """Test EnergyLogger behavior when GPU is not available."""
    from carbon_ops.energy_logger import EnergyLogger

    # Mock GPU unavailability
    logger = EnergyLogger()
    logger.gpu_available = False
    logger.gpu_count = 0

    gpu_metrics = logger.get_gpu_metrics()
    assert gpu_metrics == []

    metric = logger.log_metrics("no_gpu_test")
    assert metric["gpu"] == []


def test_monitor_energy_calculation():
    """Test energy calculation in monitor context manager."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    with logger.monitor("energy_calc_test"):
        import time

        time.sleep(0.1)  # Short sleep for measurable duration

    metric = logger.metrics[-1]  # End metric
    assert "energy" in metric

    energy_data = metric["energy"]
    assert "duration_seconds" in energy_data
    assert "avg_power_watts" in energy_data
    assert "energy_wh_total" in energy_data
    assert "energy_wh_active" in energy_data
    assert "allocation_ratio" in energy_data
    assert "attribution_mode" in energy_data

    # Duration should be > 0
    assert energy_data["duration_seconds"] > 0

    # Energy should be reasonable (not negative, not infinite)
    assert energy_data["energy_wh_total"] >= 0
    assert energy_data["energy_wh_active"] >= 0


def test_monitor_uses_governor_allocation_ratio(monkeypatch):
    """Governor integration should compute allocation ratios when available."""

    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()
    logger.gpu_available = False

    snapshots = iter(
        [
            GovernorSnapshot(timestamp=0.0, counters_uj={"package-0": 1_000_000_000}),
            GovernorSnapshot(timestamp=1.0, counters_uj={"package-0": 4_600_000_000}),
        ]
    )
    cpu_samples = iter(
        [
            _CpuTimesSample(process_seconds=100.0, total_seconds=1000.0),
            _CpuTimesSample(process_seconds=130.0, total_seconds=1100.0),
        ]
    )

    monkeypatch.setattr(
        type(logger),
        "_take_governor_snapshot",
        lambda self: next(snapshots, None),
    )
    monkeypatch.setattr(
        type(logger),
        "_sample_cpu_times",
        lambda self: next(cpu_samples, None),
    )

    perf_iter = iter([10.0, 11.0])
    monkeypatch.setattr(
        telemetry_logger.time,
        "perf_counter",
        lambda: next(perf_iter),
    )

    with logger.monitor("governor_test"):
        pass

    energy = logger.metrics[-1]["energy"]
    assert energy["attribution_mode"] == "governor_cpu_time"
    assert energy["allocation_ratio"] == pytest.approx(0.3, rel=1e-6)
    assert energy["cpu_energy_wh"] == pytest.approx(1.0, rel=1e-6)


def test_logger_metrics_history_limit():
    """Test that metrics are properly limited by history_limit."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger(history_limit=5)

    for i in range(10):
        logger.log_metrics(f"test_{i}")

    assert len(logger.metrics) == 5  # Should only keep last 5


def test_get_cpu_metrics_error_handling():
    """Test CPU metrics collection error handling."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    # This should not crash even if psutil calls fail
    metrics = logger.get_cpu_metrics()
    assert isinstance(metrics, dict)
    # Should have some reasonable defaults
    assert "cpu_percent" in metrics
    assert "cpu_freq_mhz" in metrics
    assert "estimated_power_watts" in metrics


def test_get_memory_metrics():
    """Test memory metrics collection."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    metrics = logger.get_memory_metrics()
    assert isinstance(metrics, dict)
    assert "memory_used_gb" in metrics
    assert "memory_percent" in metrics
    assert "memory_available_gb" in metrics

    # Values should be reasonable
    assert metrics["memory_percent"] >= 0
    assert metrics["memory_percent"] <= 100
    assert metrics["memory_used_gb"] >= 0
    assert metrics["memory_available_gb"] >= 0


def test_logger_export_metrics():
    """Test metrics export functionality."""
    import tempfile
    from pathlib import Path
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    # Add some metrics
    logger.log_metrics("export_test_1")
    logger.log_metrics("export_test_2")

    with tempfile.TemporaryDirectory() as tmp_dir:
        export_path = Path(tmp_dir) / "exported_metrics.json"

        logger.export_metrics(str(export_path))

        assert export_path.exists()

        import json

        with open(export_path, "r") as f:
            data = json.load(f)

        assert "summary" in data
        assert "metrics" in data
        assert len(data["metrics"]) == 2


def test_logger_get_metrics_summary():
    """Test metrics summary generation."""
    from carbon_ops.energy_logger import EnergyLogger

    logger = EnergyLogger()

    # Empty logger
    summary = logger.get_metrics_summary()
    assert summary["message"] == "No metrics collected yet"

    # Add metrics
    logger.log_metrics("summary_test_1")
    logger.log_metrics("summary_test_2")

    summary = logger.get_metrics_summary()
    assert "total_measurements" in summary
    assert summary["total_measurements"] == 2
    assert "average_cpu_percent" in summary
    assert "average_memory_percent" in summary
    assert "average_power_watts" in summary
    assert "gpu_monitoring_enabled" in summary
