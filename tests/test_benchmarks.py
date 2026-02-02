"""
Performance benchmarks for high-throughput scenarios.

Uses pytest-benchmark to measure performance of core operations.
"""

import tempfile
from pathlib import Path

import pytest

pytest.importorskip(
    "pytest_benchmark", reason="pytest-benchmark plugin is required for benchmark tests"
)

from carbon_ops.energy_logger import EnergyLogger
from carbon_ops.carbon_estimator import CarbonEstimator
from carbon_ops.ledger_writer import append_carbon_estimate
from carbon_ops.tools.verify import Signer


class TestPerformanceBenchmarks:
    """Performance benchmarks for carbon tracking operations."""

    @pytest.fixture
    def estimator(self):
        return CarbonEstimator()

    @pytest.fixture
    def logger(self):
        return EnergyLogger()

    @pytest.fixture
    def signer(self):
        return Signer(bytes(range(32)))

    def test_benchmark_energy_logging(self, benchmark, logger):
        """Benchmark energy metric collection."""

        def log_metrics():
            return logger.log_metrics("benchmark_test")

        result = benchmark(log_metrics)
        assert result["operation"] == "benchmark_test"
        assert "cpu" in result
        assert "memory" in result

    def test_benchmark_carbon_estimation_simple(self, benchmark, estimator):
        """Benchmark simple carbon estimation from energy."""
        energy_wh = 1000.0

        def estimate():
            return estimator.estimate_from_energy(energy_wh)

        result = benchmark(estimate)
        assert result["energy_consumed_kwh"] == 1.0
        assert result["carbon_emissions_gco2"] >= 0

    def test_benchmark_carbon_estimation_time_span(self, benchmark, estimator):
        """Benchmark carbon estimation over time span."""
        from datetime import datetime, timedelta

        start_ts = datetime(2023, 1, 1)
        end_ts = start_ts + timedelta(hours=1)
        power_watts = 100.0

        def estimate():
            return estimator.estimate_over_span(
                start_ts=start_ts, end_ts=end_ts, power_watts=power_watts
            )

        result = benchmark(estimate)
        assert result["energy_consumed_kwh"] == 0.1  # 100W * 1 hour = 0.1 kWh
        assert result["carbon_emissions_gco2"] >= 0

    def test_benchmark_ledger_append(self, benchmark, estimator, signer):
        """Benchmark ledger append operations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger_path = Path(tmp_dir) / "benchmark_ledger.ndjson"

            # Pre-create estimate to benchmark just the append
            estimate = estimator.estimate_from_energy(1000.0)

            def append():
                return append_carbon_estimate(
                    ledger_path, estimate, signer, include_prev_hash=True
                )

            result = benchmark(append)
            assert "signature" in result
            assert ledger_path.exists()

    def test_benchmark_high_frequency_logging(self, benchmark, logger):
        """Benchmark high-frequency energy logging."""
        operations = [f"op_{i}" for i in range(100)]

        logger.metrics.clear()

        def log_multiple():
            for op in operations:
                logger.log_metrics(op)

        initial_len = len(logger.metrics)
        benchmark(log_multiple)
        added = len(logger.metrics) - initial_len
        assert added >= len(operations)
        assert added % len(operations) == 0

    def test_benchmark_concurrent_estimation(self, benchmark, estimator):
        """Benchmark multiple carbon estimations."""
        energies = [100.0 * i for i in range(1, 101)]  # 100 different values

        def estimate_multiple():
            results = []
            for energy in energies:
                result = estimator.estimate_from_energy(energy)
                results.append(result)
            return results

        results = benchmark(estimate_multiple)
        assert len(results) == 100
        assert all(r["carbon_emissions_gco2"] >= 0 for r in results)

    @pytest.mark.parametrize("num_operations", [10, 50, 100])
    def test_benchmark_bulk_ledger_operations(
        self, benchmark, estimator, signer, num_operations
    ):
        """Benchmark bulk ledger operations with varying sizes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger_path = Path(tmp_dir) / f"bulk_{num_operations}_ledger.ndjson"

            # Pre-create estimates
            estimates = [
                estimator.estimate_from_energy(100.0 * i) for i in range(num_operations)
            ]

            def bulk_append():
                for estimate in estimates:
                    append_carbon_estimate(
                        ledger_path, estimate, signer, include_prev_hash=True
                    )

            benchmark(bulk_append)
            assert ledger_path.exists()

            # Verify all entries
            lines = ledger_path.read_text().strip().split("\n")
            assert len(lines) >= num_operations
            assert len(lines) % num_operations == 0

    def test_benchmark_memory_usage_stability(self, benchmark, logger):
        """Benchmark memory usage stability during extended logging."""
        # Clear existing metrics
        logger.metrics.clear()

        def log_extended():
            for i in range(1000):
                logger.log_metrics(f"mem_test_{i}")

        initial_len = len(logger.metrics)
        benchmark(log_extended)
        total_len = len(logger.metrics)
        assert total_len - initial_len >= 1000
        assert (total_len - initial_len) % 1000 == 0

        # Check memory metrics are reasonable
        for metric in logger.metrics[-10:]:  # Check last 10
            assert metric["memory"]["memory_percent"] >= 0
            assert metric["memory"]["memory_percent"] <= 100

    def test_benchmark_large_time_span_estimation(self, benchmark, estimator):
        """Benchmark estimation over large time spans with many buckets."""
        from datetime import datetime, timedelta

        start_ts = datetime(2023, 1, 1)
        end_ts = start_ts + timedelta(days=30)  # 30 days
        power_watts = 50.0

        def estimate_large_span():
            return estimator.estimate_over_span(
                start_ts=start_ts,
                end_ts=end_ts,
                power_watts=power_watts,
                bucket_minutes=60,  # 1 hour buckets
            )

        result = benchmark(estimate_large_span)
        expected_energy = (
            50.0 * 24 * 30 / 1000.0
        )  # 50W * 24h/day * 30 days / 1000 = kWh
        assert abs(result["energy_consumed_kwh"] - expected_energy) < 0.1
        assert result["carbon_emissions_gco2"] >= 0
