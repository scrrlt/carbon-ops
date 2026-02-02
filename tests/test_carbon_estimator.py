"""Unit tests for CarbonEstimator core logic."""

import pytest
from datetime import datetime, timedelta
from typing import cast

from carbon_ops import CarbonEstimator
from carbon_ops.intensity_provider import IntensityProvider, IntensityReading


class MockProvider(IntensityProvider):
    """Mock intensity provider for testing."""

    def __init__(self, intensities: list[float]):
        """Initialize mock provider with intensity values."""
        super().__init__(ttl_seconds=300)
        self.intensities = intensities
        self.index = 0

    def _get_reading_uncached(self, timestamp, region):
        intensity = self.intensities[self.index % len(self.intensities)]
        self.index += 1
        return IntensityReading(intensity_gco2_kwh=intensity, provider_version="mock")


def test_estimate_over_span_weighted_intensity():
    """Test multi-bucket span estimation with varying intensities."""
    estimator = CarbonEstimator(region="US_AVERAGE")

    # 3 buckets: 15min each, intensities 400, 500, 600 g/kWh
    start_ts = datetime(2023, 1, 1, 12, 0, 0)
    end_ts = start_ts + timedelta(minutes=45)  # 45 min span

    mock_provider = MockProvider([400, 500, 600])
    estimator.intensity_provider = mock_provider

    result = estimator.estimate_over_span(
        start_ts=start_ts,
        end_ts=end_ts,
        energy_wh=1350,  # 1.35 kWh total, 0.9 kWh per bucket
        bucket_minutes=15,
        return_dataclass=True,
    )

    # Weighted average: (400*0.9 + 500*0.9 + 600*0.9) / (3*0.9) = 500
    assert result.intensity_g_per_kwh == pytest.approx(500.0, rel=1e-6)  # type: ignore
    assert result.energy_kwh == 1.35  # type: ignore
    assert result.total_energy_with_pue_kwh == 1.35 * 1.2  # default PUE  # type: ignore


def test_estimate_over_span_invalid_bucket_minutes():
    """Test that invalid bucket_minutes raises ValueError."""
    estimator = CarbonEstimator()
    start_ts = datetime(2023, 1, 1)
    end_ts = start_ts + timedelta(seconds=1)

    with pytest.raises(ValueError, match="bucket_minutes must be >= 1"):
        estimator.estimate_over_span(
            start_ts=start_ts, end_ts=end_ts, energy_wh=1.0, bucket_minutes=0
        )


def test_estimate_over_span_extreme_values():
    """Test estimate_over_span with extreme but valid values."""
    estimator = CarbonEstimator()
    start_ts = datetime(2023, 1, 1)
    end_ts = start_ts + timedelta(seconds=3600)  # 1 hour

    # Very high power
    result = cast(
        dict,
        estimator.estimate_over_span(
            start_ts=start_ts,
            end_ts=end_ts,
            power_watts=1e6,  # 1 MW
            return_dataclass=False,
        ),
    )
    expected_energy = 1000.0  # 1 MW * 1 hour = 1000 kWh
    assert abs(result["energy_consumed_kwh"] - expected_energy) < 1e-6
    assert result["carbon_emissions_gco2"] >= 0

    # Very low power
    result = cast(
        dict,
        estimator.estimate_over_span(
            start_ts=start_ts,
            end_ts=end_ts,
            power_watts=1e-6,  # 1 microwatt
            return_dataclass=False,
        ),
    )
    expected_energy_low = 1e-9  # 1e-6 W * 3600 s / 3600 / 1000 = 1e-9 kWh
    assert abs(result["energy_consumed_kwh"] - expected_energy_low) < 1e-12
    assert result["carbon_emissions_gco2"] >= 0


def test_estimate_over_span_missing_policy():
    """Test estimate_over_span with different missing policies."""
    estimator = CarbonEstimator()
    start_ts = datetime(2023, 1, 1)
    end_ts = start_ts + timedelta(hours=2)

    # Test with 'drop' policy - since no provider, all buckets dropped, so energy = 0
    result = estimator.estimate_over_span(
        start_ts=start_ts,
        end_ts=end_ts,
        energy_wh=1000.0,
        bucket_minutes=60,
        missing_policy="drop",
    )
    assert result["energy_consumed_kwh"] == 0.0

    # Test with invalid policy (should default to 'step', so use static)
    result = estimator.estimate_over_span(
        start_ts=start_ts,
        end_ts=end_ts,
        energy_wh=1000.0,
        bucket_minutes=60,
        missing_policy="invalid",
    )
    assert result["energy_consumed_kwh"] == 1.0


def test_carbon_estimator_config_loading():
    """Test CarbonEstimator with configuration loading."""
    from carbon_ops.config_loader import CarbonConfig

    config = CarbonConfig()
    config.region.default = "eu-west"
    config.pue.default = 1.3

    estimator = CarbonEstimator(config=config)
    assert estimator.region == "eu-west"
    assert estimator.pue == 1.3


def test_get_available_regions_and_datacenters():
    """Test static methods for available regions and datacenter types."""
    regions = CarbonEstimator.get_available_regions()
    assert isinstance(regions, dict)
    assert "global-average" in regions
    assert "us-east" in regions

    datacenters = CarbonEstimator.get_available_datacenter_types()
    assert isinstance(datacenters, dict)
    assert "cloud-hyperscale" in datacenters
    assert "enterprise" in datacenters


def test_compare_carbon_equivalents():
    """Test carbon equivalents calculation."""
    estimator = CarbonEstimator()

    equivalents = estimator.compare_carbon_equivalents(100.0)  # 100 kg CO2
    assert "equivalent_km_driven" in equivalents
    assert "equivalent_tree_days" in equivalents
    assert "equivalent_smartphone_charges" in equivalents

    # Test with zero
    equivalents_zero = estimator.compare_carbon_equivalents(0.0)
    assert equivalents_zero["equivalent_km_driven"] == "0.00"


def test_get_carbon_label():
    """Test carbon label generation."""
    estimator = CarbonEstimator()

    label = cast(dict, estimator.get_carbon_label(1000.0))  # 1 kWh
    assert "carbon_label" in label
    assert "rating" in label["carbon_label"]
    assert "region" in label["carbon_label"]
    assert "estimates" in label["carbon_label"]
    assert "equivalents" in label["carbon_label"]
