"""Tests for IntensityProviders using mocks to avoid real API calls."""

from unittest.mock import MagicMock, patch
from datetime import datetime
from carbon_ops.intensity_provider import (
    WattTimeProvider,
    ElectricityMapsProvider,
    UKCarbonIntensityProvider,
    StaticIntensityProvider,
)


@patch("httpx.Client")
def test_electricitymaps_provider_success(mock_client_class, monkeypatch):
    """Test ElectricityMaps provider with mocked HTTP response."""
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "carbonIntensity": 250,
        "datetime": "2023-01-01T00:00:00.000Z",
        "updatedAt": "2023-01-01T00:00:00.000Z",
    }
    mock_client.get.return_value = mock_response

    monkeypatch.setenv("ELECTRICITYMAPS_TOKEN", "fake_token")
    provider = ElectricityMapsProvider()

    reading = provider._get_reading_uncached(datetime.now(), "US-CA")
    assert reading is not None
    assert reading.intensity_gco2_kwh == 250.0
    assert reading.provider_version is not None


@patch("httpx.Client")
def test_uk_provider_success(mock_client_class):
    """Test UK provider with mocked HTTP response."""
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [{"intensity": {"actual": 150, "forecast": 160}}]
    }
    mock_client.get.return_value = mock_response

    provider = UKCarbonIntensityProvider()
    reading = provider._get_reading_uncached(datetime.now(), "UK")

    assert reading is not None
    assert reading.intensity_gco2_kwh == 160.0  # Uses forecast


@patch("httpx.Client")
def test_watttime_provider_success(mock_client_class):
    """Test WattTime provider with mocked HTTP response."""
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    # Mock data response (no auth needed in mock)
    data_response = MagicMock()
    data_response.status_code = 200
    data_response.json.return_value = {
        "freq": "300",
        "ba": "CAISO_NORTH",
        "moer": "50",
        "point_time": "2023-01-01T00:00:00Z",
    }

    mock_client.get.return_value = data_response

    provider = WattTimeProvider()
    # Set env
    import os

    os.environ["WATTTIME_USERNAME"] = "test"
    os.environ["WATTTIME_PASSWORD"] = "test"
    try:
        reading = provider._get_reading_uncached(datetime.now(), "CAISO_NORTH")
        assert reading is not None
        # Based on code: lb_per_mwh = 50, gco2_per_kwh = 0.453592 * 50
        expected_intensity = 0.453592 * 50
        assert abs(reading.intensity_gco2_kwh - expected_intensity) < 0.01
    finally:
        del os.environ["WATTTIME_USERNAME"]
        del os.environ["WATTTIME_PASSWORD"]


def test_provider_error_handling(monkeypatch):
    """Test that providers return None on HTTP errors."""
    from carbon_ops.intensity_provider import ElectricityMapsProvider

    with patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_client.get.return_value = mock_response

        monkeypatch.setenv("ELECTRICITYMAPS_TOKEN", "fake")
        provider = ElectricityMapsProvider()
        reading = provider._get_reading_uncached(datetime.now(), "US-CA")
        assert reading is None


def test_static_provider_cache_stats() -> None:
    """Static provider should track cache hits and misses."""

    mapping = {"region-1": 100.0}
    provider = StaticIntensityProvider(mapping, default=200.0, ttl_seconds=300)

    assert provider.get_cache_stats() == {"hits": 0, "misses": 0}

    provider.get_intensity(None, "region-1")
    provider.get_intensity(None, "region-1")

    stats = provider.get_cache_stats()
    assert stats["misses"] >= 1
    assert stats["hits"] >= 1
