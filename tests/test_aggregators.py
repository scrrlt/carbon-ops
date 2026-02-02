"""Tests for carbon aggregators."""

from carbon_ops.aggregators import aggregate_estimates
from carbon_ops.carbon_estimator import CarbonEstimator
from carbon_ops.carbon_models import CarbonEstimate


def test_aggregate_estimates_empty():
    """Test aggregation with empty data."""
    result = aggregate_estimates([])
    assert result == {}


def test_aggregate_estimates_single_entry():
    """Test aggregation with single entry."""
    estimator = CarbonEstimator()
    estimate = estimator.estimate_from_energy(1.0, return_dataclass=True)
    assert isinstance(estimate, CarbonEstimate)

    result = aggregate_estimates([estimate])
    assert "all" in result
    assert result["all"]["count"] == 1
    total_grams = result["all"]["total_grams"]
    assert isinstance(total_grams, (int, float)) and total_grams > 0


def test_aggregate_estimates_multiple_entries():
    """Test aggregation with multiple entries."""
    estimator = CarbonEstimator()
    estimates = []
    for _ in range(3):
        estimate = estimator.estimate_from_energy(1.0, return_dataclass=True)
        assert isinstance(estimate, CarbonEstimate)
        estimates.append(estimate)

    result = aggregate_estimates(estimates)
    assert result["all"]["count"] == 3
    total_grams = result["all"]["total_grams"]
    assert isinstance(total_grams, (int, float)) and total_grams > 0


def test_aggregate_estimates_by_region():
    """Test aggregation by region."""
    estimator = CarbonEstimator()
    estimate1 = estimator.estimate_from_energy(1.0, return_dataclass=True)
    estimate2 = estimator.estimate_from_energy(1.0, return_dataclass=True)
    assert isinstance(estimate1, CarbonEstimate)
    assert isinstance(estimate2, CarbonEstimate)

    result = aggregate_estimates([estimate1, estimate2], by="region")
    # Both should be in same region
    assert len(result) == 1
    region_key = list(result.keys())[0]
    assert result[region_key]["count"] == 2
