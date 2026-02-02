"""Tests for carbon_taxonomy logic to improve coverage."""

from unittest.mock import MagicMock
from carbon_ops.carbon_taxonomy import CarbonTaxonomyLogger, get_theta_regime


def test_get_theta_regime():
    """Test theta regime classification."""
    assert get_theta_regime(0.05) == "operational_dominated"
    assert get_theta_regime(0.20) == "marginal"
    assert get_theta_regime(0.40) == "embodied_dominated"


def test_taxonomy_full_lifecycle_mock_bq():
    """Test taxonomy logger with mocked BigQuery."""
    mock_bq = MagicMock()
    mock_table = MagicMock()
    mock_bq.dataset.return_value.table.return_value = mock_table
    mock_bq.insert_rows_json.return_value = []  # No errors

    logger = CarbonTaxonomyLogger(
        device_type="cloud_vm", bigquery_table="dataset.table", gcp_project="test-proj"
    )
    # Inject mock
    logger.bq_client = mock_bq

    with logger.track_operation("training_run", "op_123"):
        pass

    # Verify measurements were created
    assert len(logger.measurements) == 1
    assert logger.measurements[0].operation_id == "op_123"
    assert logger.measurements[0].operation_type == "training_run"

    # Verify BQ insert was called
    assert mock_bq.insert_rows_json.called


def test_taxonomy_summary_stats():
    """Test taxonomy summary calculation."""
    logger = CarbonTaxonomyLogger()

    # Manually create measurements or run operations
    with logger.track_operation("test", "1"):
        pass
    with logger.track_operation("test", "2"):
        pass

    summary = logger.get_taxonomy_summary()
    assert summary["measurement_count"] == 2
    assert "avg_theta" in summary
    assert "min_theta" in summary
    assert "max_theta" in summary
    assert "total_operational_kg" in summary
    assert "total_embodied_kg" in summary
    assert "dominant_class" in summary
    assert "optimization_viable_pct" in summary


def test_taxonomy_export_to_json(tmp_path):
    """Test JSON export functionality."""
    logger = CarbonTaxonomyLogger()

    with logger.track_operation("export_test", "exp_1"):
        pass

    outfile = tmp_path / "taxonomy.json"
    logger.export_to_json(str(outfile))

    assert outfile.exists()
    # Could parse and verify contents, but basic existence check for now


def test_taxonomy_complexity_classification():
    """Test complexity classification logic."""
    logger = CarbonTaxonomyLogger()

    # Test different theta values
    # This would require mocking the embodied data, but for now just check the method exists
    assert hasattr(logger, "_classify_complexity")

    # Test with known values
    assert logger._classify_complexity(0.05) == "C-P[operational-dominated]"
    assert logger._classify_complexity(0.20) == "C-P[marginal]"
    assert logger._classify_complexity(0.40) == "C-NP[embodied-dominated]"
