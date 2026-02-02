"""Tests for embodied carbon database."""

from carbon_ops.embodied_carbon_db import (
    get_embodied_carbon,
    calculate_embodied_for_operation,
)


def test_get_embodied_carbon_known_device():
    """Test embodied carbon lookup for known device."""
    result = get_embodied_carbon("cloud_vm", "cpu_only")
    assert result is not None
    assert result.total_kg_co2e == 200.0
    assert result.amortization_days == 1825
    assert result.source == "Masanet et al. 2020"


def test_get_embodied_carbon_unknown_device():
    """Test embodied carbon lookup for unknown device."""
    result = get_embodied_carbon("unknown", "device")
    assert result is None


def test_calculate_embodied_for_operation():
    """Test embodied carbon calculation for operation."""
    result = calculate_embodied_for_operation("cloud_vm", "cpu_only", 3600.0)  # 1 hour
    assert isinstance(result, dict)
    assert "embodied_kg" in result
    assert "total_lifetime_kg" in result
    assert result["total_lifetime_kg"] == 200.0
    assert result["embodied_kg"] > 0


def test_calculate_embodied_for_operation_unknown_device():
    """Test embodied carbon calculation for unknown device."""
    result = calculate_embodied_for_operation("unknown", "device", 3600.0)
    assert result["embodied_kg"] == 0.0
    assert result["total_lifetime_kg"] == 0.0
    assert result["confidence"] == "none"
