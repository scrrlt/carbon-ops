"""Tests for Monte Carlo analysis."""

from carbon_ops.monte_carlo import (
    estimate_co2_distribution,
    bootstrap_ci,
    power_analysis_required_n,
    monte_carlo_summary,
)


def test_estimate_co2_distribution():
    """Test CO2 distribution estimation."""
    result = estimate_co2_distribution(
        duration_s=3600.0,  # 1 hour
        start_power_w=100.0,
        end_power_w=100.0,
        n=10,
    )
    assert isinstance(result, list)
    assert len(result) == 10
    assert all(isinstance(x, float) for x in result)
    assert all(x >= 0 for x in result)


def test_bootstrap_ci():
    """Test bootstrap confidence interval."""
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    ci_low, ci_high = bootstrap_ci(samples, alpha=0.05, iters=100)
    assert isinstance(ci_low, float)
    assert isinstance(ci_high, float)
    assert ci_low <= ci_high
    # With small sample, CI should include most values
    assert ci_low <= 3.0 <= ci_high


def test_bootstrap_ci_empty():
    """Test bootstrap CI with empty samples."""
    ci_low, ci_high = bootstrap_ci([])
    assert ci_low == 0.0
    assert ci_high == 0.0


def test_power_analysis_required_n():
    """Test sample size calculation for power analysis."""
    n = power_analysis_required_n(stddev=1.0, effect=0.5)
    assert isinstance(n, int)
    assert n >= 2


def test_monte_carlo_summary_metadata():
    """Monte Carlo summary should surface confidence interval metadata."""

    samples = [1.0, 2.0, 3.0, 4.0]
    meta = monte_carlo_summary(samples, iters=128, seed=7)
    assert meta["method"] == "monte_carlo"
    assert meta["confidence_level_pct"] == 95.0
    assert meta["ci_lower_g"] >= 0.0
    assert meta["ci_lower_g"] <= meta["ci_upper_g"]
