"""Tests for power configuration loading."""

from carbon_ops.carbon_taxonomy import (
    POWER_ESTIMATES,
    GRID_INTENSITIES,
    CarbonTaxonomyLogger,
)


def test_power_estimates_loaded():
    """Test that power estimates are loaded correctly."""
    assert isinstance(POWER_ESTIMATES, dict)
    assert "cloud_vm" in POWER_ESTIMATES
    assert "gpu_a100" in POWER_ESTIMATES.get("cloud_vm", {})


def test_estimate_energy_uses_config():
    """Test that energy estimation uses the configuration."""
    logger = CarbonTaxonomyLogger(device_type="cloud_vm", device_subtype="cpu_only")
    # duration 3600 seconds should convert power_kw * 1 hour
    duration = 3600
    energy = logger._estimate_energy(duration)
    expected_kw = POWER_ESTIMATES.get("cloud_vm", {}).get("cpu_only", 0.1)
    assert abs(energy - expected_kw * (duration / 3600.0)) < 1e-9


def test_grid_intensity_loaded():
    """Test that grid intensities are loaded correctly."""
    assert isinstance(GRID_INTENSITIES, dict)
    assert GRID_INTENSITIES.get("US_AVERAGE") == 385
