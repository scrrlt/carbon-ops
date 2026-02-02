"""Tests for energy logger type checking."""

from carbon_ops.energy_logger import EnergyLogger


def test_log_metrics_returns_typed_dict():
    """Test that log_metrics returns a properly typed dictionary."""
    logger = EnergyLogger()
    m = logger.log_metrics("unit")
    assert isinstance(m, dict)
    # Basic shape checks
    assert "timestamp" in m
    assert "operation" in m and m["operation"] == "unit"
    assert isinstance(m.get("cpu"), dict)
    assert isinstance(m.get("memory"), dict)
    assert isinstance(m.get("gpu"), list)


def test_get_metrics_summary_shape():
    """Test the shape of the metrics summary dictionary."""
    logger = EnergyLogger()
    logger.log_metrics("a")
    s = logger.get_metrics_summary()
    assert isinstance(s, dict)
    assert "total_measurements" in s
    assert "average_cpu_percent" in s
