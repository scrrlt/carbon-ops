"""
Integration tests for end-to-end carbon tracking pipeline.

Tests the full workflow: energy logging -> carbon estimation -> ledger persistence.
"""

import tempfile
import time
from pathlib import Path

import pytest

from carbon_ops.energy_logger import EnergyLogger
from carbon_ops.carbon_estimator import CarbonEstimator
from carbon_ops.ledger_writer import append_carbon_estimate
from carbon_ops.tools.verify import Signer
from carbon_ops.tools.ledger import validate_ledger


def test_end_to_end_pipeline():
    """Test complete pipeline from energy monitoring to ledger persistence."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "carbon_ledger.ndjson"

        # Initialize components
        logger = EnergyLogger()
        estimator = CarbonEstimator()
        signer = Signer(bytes(range(32)))

        # Step 1: Monitor energy consumption
        operation = "integration_test_operation"
        with logger.monitor(operation):
            # Simulate some work
            time.sleep(0.1)
            # The monitoring context will automatically collect end metrics

        # Verify we have metrics (start and end)
        assert len(logger.metrics) == 2
        # Get the end metric which contains energy calculation
        end_metric = logger.metrics[-1]
        assert end_metric["operation"] == f"{operation}_end"
        assert "energy" in end_metric

        # Step 2: Estimate carbon from energy data
        energy_wh = end_metric["energy"]["energy_wh_total"]
        carbon_estimate = estimator.estimate_from_energy(
            energy_wh, return_dataclass=True
        )

        # Verify carbon estimate
        assert hasattr(carbon_estimate, "grams")
        assert carbon_estimate.grams >= 0

        # Step 3: Persist to ledger
        signed = append_carbon_estimate(
            ledger_path, carbon_estimate, signer, include_prev_hash=True
        )

        # Verify ledger persistence
        assert ledger_path.exists()
        assert ledger_path.stat().st_size > 0

        # Validate ledger integrity
        ok, bad_line = validate_ledger(ledger_path, signer.signing_key)
        assert ok, f"Ledger validation failed at line {bad_line}"

        # Verify the signed entry contains expected data
        assert "kind" in signed
        assert signed["kind"] == "carbon_ops"
        assert "schema_version" in signed
        assert "signature" in signed
        assert "signing_key" in signed


def test_multiple_operations_pipeline():
    """Test pipeline with multiple operations and ledger chaining."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "multi_op_ledger.ndjson"

        logger = EnergyLogger()
        estimator = CarbonEstimator()
        signer = Signer(bytes(range(32)))

        operations = ["op1", "op2", "op3"]

        for op in operations:
            # Monitor each operation
            with logger.monitor(op):
                time.sleep(0.05)

            # Get the latest metric
            metric = logger.metrics[-1]
            energy_wh = metric["energy"]["energy_wh_total"]

            # Estimate carbon
            carbon_estimate = estimator.estimate_from_energy(
                energy_wh, return_dataclass=True
            )
            # Append to ledger
            append_carbon_estimate(
                ledger_path, carbon_estimate, signer, include_prev_hash=True
            )

        # Validate entire ledger
        ok, bad_line = validate_ledger(ledger_path, signer.signing_key)
        assert ok, f"Ledger validation failed at line {bad_line}"

        # Verify we have entries for all operations
        lines = ledger_path.read_text().strip().split("\n")
        assert len(lines) == len(operations)


def test_pipeline_with_custom_config():
    """Test pipeline with custom configuration settings."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "custom_config_ledger.ndjson"

        # Custom estimator with different region and PUE
        estimator = CarbonEstimator(
            region="eu-north", datacenter_type="edge", custom_pue=1.1
        )

        logger = EnergyLogger()
        signer = Signer(bytes(range(32)))

        with logger.monitor("custom_config_test"):
            time.sleep(0.1)

        metric = logger.metrics[-1]
        energy_wh = metric["energy"]["energy_wh_total"]

        carbon_estimate = estimator.estimate_from_energy(
            energy_wh, return_dataclass=True
        )
        append_carbon_estimate(
            ledger_path, carbon_estimate, signer, include_prev_hash=True
        )

        # Validate
        ok, _ = validate_ledger(ledger_path, signer.signing_key)
        assert ok


@pytest.mark.parametrize("use_dataclass", [True, False])
def test_pipeline_dataclass_vs_dict(use_dataclass):
    """Test pipeline works with both dataclass and dict return formats."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "dataclass_test.ndjson"

        logger = EnergyLogger()
        estimator = CarbonEstimator()
        signer = Signer(bytes(range(32)))

        with logger.monitor("dataclass_test"):
            time.sleep(0.1)

        metric = logger.metrics[-1]
        energy_wh = metric["energy"]["energy_wh_total"]

        carbon_estimate = estimator.estimate_from_energy(
            energy_wh, return_dataclass=use_dataclass
        )

        append_carbon_estimate(
            ledger_path, carbon_estimate, signer, include_prev_hash=True
        )

        ok, _ = validate_ledger(ledger_path, signer.signing_key)
        assert ok


def test_append_carbon_estimate_rejects_unknown_extra(tmp_path: Path) -> None:
    """Unknown extra fields should fail validation before writing."""

    estimator = CarbonEstimator()
    signer = Signer(bytes(range(32)))
    ledger_path = tmp_path / "invalid_extra.ndjson"

    estimate = estimator.estimate_from_energy(1.0, return_dataclass=True)

    with pytest.raises(RuntimeError):
        append_carbon_estimate(
            ledger_path,
            estimate,
            signer,
            extra={"bogus": "value"},
        )


def test_append_carbon_estimate_allows_schema_labels(tmp_path: Path) -> None:
    """Schema fields such as labels can be provided via extra metadata."""

    estimator = CarbonEstimator()
    signer = Signer(bytes(range(32)))
    ledger_path = tmp_path / "labels_extra.ndjson"

    estimate = estimator.estimate_from_energy(1.0, return_dataclass=True)

    signed = append_carbon_estimate(
        ledger_path,
        estimate,
        signer,
        extra={"labels": {"project": "archimedes"}},
    )

    assert signed["labels"] == {"project": "archimedes"}
    ok, _ = validate_ledger(ledger_path, signer.signing_key)
    assert ok
