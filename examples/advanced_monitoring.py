#!/usr/bin/env python3
"""
Advanced Energy Monitoring Example

This example demonstrates advanced usage of the EnergyLogger with:
- Custom configuration
- GPU monitoring (if available)
- Metric export and analysis
- Real-time monitoring patterns
"""

import os
import time
from pathlib import Path

from carbon_ops.energy_logger import EnergyLogger


def monitor_ml_training():
    """Monitor a machine learning training session."""
    print("Starting ML Training Energy Monitor")

    logger = EnergyLogger()

    # Calibrate idle power (optional but recommended)
    print("Calibrating idle power baseline...")
    idle_power = logger.calibrate_idle(samples=5, interval=0.2)
    if idle_power:
        print(f"Idle baseline: {idle_power:.2f}W")
    else:
        print("Idle calibration failed, using default baseline")

    # Training simulation
    print("Starting training simulation...")

    with logger.monitor("ml_training_epoch_1"):
        print("Training model (simulated)...")
        # Simulate training work
        time.sleep(2.0)

        # Log intermediate metrics
        mid_metrics = logger.log_metrics(
            "training_checkpoint", {"epoch": 1, "loss": 0.234, "accuracy": 0.89}
        )
        checkpoint_energy = mid_metrics["energy"]["energy_wh_total"]
        print(f"Checkpoint energy usage: {checkpoint_energy:.4f} Wh")
        print(
            f"Training completed. Total energy: {logger.metrics[-1]['energy']['energy_wh_total']:.4f} Wh"
        )

    # Export metrics
    export_path = Path("training_metrics.json")
    logger.export_metrics(str(export_path))
    print(f"Metrics exported to {export_path}")

    return logger


def monitor_batch_processing():
    """Monitor batch processing with multiple operations."""
    print("Starting Batch Processing Monitor")

    logger = EnergyLogger()

    operations = [
        ("data_preprocessing", 1.5),
        ("feature_extraction", 2.0),
        ("model_inference", 0.8),
        ("result_postprocessing", 1.2),
    ]

    total_energy = 0.0

    for op_name, duration in operations:
        print(f"Processing: {op_name}...")
        with logger.monitor(op_name):
            time.sleep(duration)

        # Get the energy for this operation
        metric = logger.metrics[-1]
        energy = metric["energy"]["energy_wh_total"]
        total_energy += energy
        print(f"Operation {op_name}: {energy:.4f} Wh")

    print(f"Total batch processing energy: {total_energy:.4f} Wh")

    return logger


def analyze_energy_patterns(logger):
    """Analyze collected energy metrics."""
    print("Analyzing Energy Patterns")

    if not logger.metrics:
        print("No metrics to analyze")
        return

    summary = logger.get_metrics_summary()
    print(f"Total measurements: {summary['total_measurements']}")
    print(f"Average CPU usage: {summary['average_cpu_percent']:.1f}%")
    print(f"Average memory usage: {summary['average_memory_percent']:.1f}%")
    print(f"Average power: {summary['average_power_watts']:.2f}W")

    # Find highest energy operation
    max_energy_op = max(
        logger.metrics, key=lambda m: m.get("energy", {}).get("energy_wh_total", 0)
    )
    print(
        f"Highest energy operation: {max_energy_op['operation']} "
        f"({max_energy_op.get('energy', {}).get('energy_wh_total', 0):.4f} Wh)"
    )

    # GPU analysis if available
    gpu_operations = [m for m in logger.metrics if m.get("gpu")]
    if gpu_operations:
        print(f"Operations with GPU data: {len(gpu_operations)}")
        avg_gpu_power = sum(
            sum(g.get("power_watts", 0) for g in m["gpu"]) / len(m["gpu"])
            for m in gpu_operations
            if m["gpu"]
        ) / len(gpu_operations)
        print(f"Average GPU power: {avg_gpu_power:.2f}W")


def custom_configuration_example():
    """Example with custom TDP and monitoring settings."""
    print("Custom Configuration Example")

    original_tdp = os.environ.get("CPU_TDP_WATTS")
    os.environ["CPU_TDP_WATTS"] = "125.0"  # Custom TDP for high-end CPU

    try:
        logger = EnergyLogger()

        print("Custom TDP set to 125W")
        metrics = logger.log_metrics("custom_config_test")

        estimated_power = metrics["cpu"]["estimated_power_watts"]
        print(f"Estimated CPU power: {estimated_power:.2f}W")
    finally:
        if original_tdp is None:
            os.environ.pop("CPU_TDP_WATTS", None)
        else:
            os.environ["CPU_TDP_WATTS"] = original_tdp

    return logger


def main():
    """Run all examples."""
    print("Carbon Ops - Advanced Energy Monitoring Examples")
    print("=" * 55)

    try:
        # Example 1: ML Training
        training_logger = monitor_ml_training()

        # Example 2: Batch Processing
        batch_logger = monitor_batch_processing()

        # Example 3: Custom Configuration
        custom_logger = custom_configuration_example()

        # Analyze all collected metrics
        all_loggers = [training_logger, batch_logger, custom_logger]
        for i, logger in enumerate(all_loggers, 1):
            print(f"Logger {i} Analysis:")
            analyze_energy_patterns(logger)

        print("All examples completed successfully.")
        print("Tips:")
        print("- Use calibrate_idle() for more accurate active energy measurements")
        print("- Export metrics regularly for long-running applications")
        print("- Monitor GPU power for ML workloads when available")
        print("- Set CPU_TDP_WATTS environment variable for custom CPU power models")

    except Exception as e:
        print(f"Example failed: {e}")
        raise


if __name__ == "__main__":
    main()
