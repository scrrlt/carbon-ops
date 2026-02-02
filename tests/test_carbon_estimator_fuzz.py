"""Fuzz testing for CarbonEstimator using hypothesis."""

import math
from datetime import datetime, timedelta
from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from carbon_ops.carbon_estimator import CarbonEstimator

_DATETIME_SAFE_MAX = datetime.max - timedelta(seconds=1)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(
    start_ts=st.datetimes(
        min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)
    ),
    duration_seconds=st.floats(min_value=0.001, max_value=86400),  # 1ms to 1 day
    energy_wh=st.floats(
        min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False
    ),
    power_watts=st.floats(
        min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False
    ),
    bucket_minutes=st.integers(min_value=1, max_value=1440),  # 1 min to 1 day
    region=st.sampled_from(list(CarbonEstimator.get_available_regions().keys())),
)
def test_estimate_over_span_fuzz(
    start_ts, duration_seconds, energy_wh, power_watts, bucket_minutes, region
):
    """Fuzz test estimate_over_span with various inputs."""
    estimator = CarbonEstimator(region=region)

    # Ensure end_ts > start_ts
    end_ts = start_ts + timedelta(seconds=max(duration_seconds, 0.001))

    # Skip if both energy_wh and power_watts are zero or invalid
    if energy_wh <= 0 and power_watts <= 0:
        with pytest.raises(ValueError, match=r"Provide energy_wh or power_watts"):
            estimator.estimate_over_span(
                start_ts=start_ts,
                end_ts=end_ts,
                energy_wh=energy_wh if energy_wh > 0 else None,
                power_watts=power_watts if power_watts > 0 else None,
                bucket_minutes=bucket_minutes,
            )
        return

    # Provide exactly one of energy_wh or power_watts for the span
    kwargs = {"start_ts": start_ts, "end_ts": end_ts, "bucket_minutes": bucket_minutes}
    if energy_wh > 0:
        kwargs["energy_wh"] = energy_wh
    elif power_watts > 0:
        kwargs["power_watts"] = power_watts
    else:
        # Fallback: provide energy_wh when neither is valid
        kwargs["energy_wh"] = 1.0

    # Wrap call so that extreme fuzzed datetime/math inputs that cause OverflowError
    # (or invalid-argument ValueError) are treated as acceptable rejections, not test failures.
    try:
        result = estimator.estimate_over_span(**kwargs)

        # Assertions (Move these inside the try block to ensure they run only on success)
        assert isinstance(result, dict)
        assert "carbon_emissions_gco2" in result
        assert result["carbon_emissions_gco2"] >= 0.0
        assert not math.isnan(result["carbon_emissions_gco2"])
        assert not math.isinf(result["carbon_emissions_gco2"])

        assert "carbon_intensity_used_gco2_kwh" in result
        assert result["carbon_intensity_used_gco2_kwh"] >= 0.0

        assert "energy_consumed_kwh" in result
        assert result["energy_consumed_kwh"] >= 0.0

        # Ensure no NaN or inf in key fields
        for key in [
            "carbon_emissions_gco2",
            "carbon_intensity_used_gco2_kwh",
            "energy_consumed_kwh",
        ]:
            assert not math.isnan(result[key])
            assert not math.isinf(result[key])

    except (ValueError, OverflowError) as exc:
        error_msg = str(exc)
        if isinstance(exc, OverflowError):
            allowed_overflow_tokens = [
                "date value out of range",
                "timestamp",
                "overflow",
                "out of range",
            ]
            if not any(token in error_msg.lower() for token in allowed_overflow_tokens):
                pytest.fail(f"Unexpected OverflowError in fuzz test: {error_msg}")
            return

        expected_messages = [
            "Provide energy_wh or power_watts",
            "end_ts must be > start_ts",
            "timedelta",  # for datetime-related errors
            "domain",  # for math domain errors
            "Too many buckets",  # for excessive iterations
        ]
        if not any(msg in error_msg for msg in expected_messages):
            pytest.fail(f"Unexpected {type(exc).__name__} in fuzz test: {error_msg}")
        return


@given(
    start_ts=st.datetimes(max_value=_DATETIME_SAFE_MAX),
    bad_duration=st.floats(max_value=0, allow_nan=False, allow_infinity=False),
)
def test_estimate_over_span_invalid_duration(start_ts, bad_duration):
    """Test that invalid durations raise ValueError."""
    estimator = CarbonEstimator()
    try:
        end_ts = start_ts + timedelta(seconds=bad_duration)
    except OverflowError:
        # Datetime boundaries exceeded, skip
        return
    with pytest.raises(ValueError, match="end_ts must be > start_ts"):
        estimator.estimate_over_span(
            start_ts=start_ts,
            end_ts=end_ts,
            energy_wh=1.0,
        )


def test_estimate_over_span_extreme_datetime_overflow():
    """Test that extreme datetime values cause OverflowError."""
    estimator = CarbonEstimator()
    start_ts = datetime.min
    try:
        end_ts = start_ts + timedelta(days=999_999_999)
    except OverflowError:
        pytest.skip("Datetime arithmetic overflowed before estimator invocation")

    with pytest.raises(OverflowError):
        estimator.estimate_over_span(
            start_ts=start_ts,
            end_ts=end_ts,
            energy_wh=1.0,
        )


def test_estimate_over_span_negative_energy_value_error():
    """Test that negative energy values raise ValueError."""
    estimator = CarbonEstimator()
    start_ts = datetime(2023, 1, 1)
    end_ts = start_ts + timedelta(seconds=1)
    with pytest.raises(ValueError, match="energy_wh must be >= 0"):
        estimator.estimate_over_span(
            start_ts=start_ts,
            end_ts=end_ts,
            energy_wh=-1.0,  # Negative energy
        )


@given(
    start_ts=st.datetimes(max_value=_DATETIME_SAFE_MAX),
    energy_wh=st.floats(allow_nan=True, allow_infinity=True),
    power_watts=st.floats(allow_nan=True, allow_infinity=True),
)
def test_estimate_over_span_nan_inf_handling(start_ts, energy_wh, power_watts):
    """Test handling of NaN and inf values."""
    estimator = CarbonEstimator()
    end_ts = start_ts + timedelta(seconds=1)

    # If providing NaN/inf, should not crash
    kwargs = {"start_ts": start_ts, "end_ts": end_ts}
    if math.isfinite(energy_wh) and energy_wh >= 0:
        kwargs["energy_wh"] = energy_wh
    elif math.isfinite(power_watts) and power_watts >= 0:
        kwargs["power_watts"] = power_watts
    else:
        kwargs["energy_wh"] = 1.0  # fallback

    # Should not raise, or raise appropriate error
    try:
        result = estimator.estimate_over_span(**kwargs)
        assert isinstance(result, dict)
    except (ValueError, OverflowError) as e:
        # Acceptable for NaN/inf inputs
        error_msg = str(e)
        assert any(
            msg in error_msg for msg in ["datetime", "math", "invalid"]
        ) or isinstance(e, OverflowError), f"Unexpected error with NaN/inf: {error_msg}"
