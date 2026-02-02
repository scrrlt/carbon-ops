"""Tests for anomaly detection."""

from carbon_ops.anomaly import detect_anomalies


def test_detect_no_data():
    """Test anomaly detection with empty series."""
    assert detect_anomalies([], window=5) == (False, 0.0)


def test_detect_flat_series_no_anomaly():
    """Test anomaly detection on flat series."""
    series = [1.0, 1.0, 1.0, 1.0]
    ok, z = detect_anomalies(series, window=4, z_thresh=3.0)
    assert ok is False
    assert z == 0.0


def test_detect_spike_in_series():
    """Test anomaly detection on series with spike."""
    series = [1.0, 1.1, 0.9, 1.0, 10.0]
    ok, z = detect_anomalies(series, window=5, z_thresh=3.0)
    assert ok is True
    assert z > 3.0


def test_small_window():
    """Test anomaly detection with small window."""
    series = [1.0, 2.0]
    ok, z = detect_anomalies(series, window=5, z_thresh=1.0)
    assert isinstance(ok, bool)
    assert isinstance(z, float)
