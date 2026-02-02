#!/usr/bin/env python3
"""
Ledger Operations Example

This example demonstrates:
- Creating and signing carbon estimates
- Appending to a transparent ledger
- Validating ledger integrity
- Searching and analyzing ledger entries
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from carbon_ops.carbon_estimator import CarbonEstimator
from carbon_ops.ledger_writer import append_carbon_estimate
from carbon_ops.tools.ledger import validate_ledger
from carbon_ops.tools.verify import Signer


def create_sample_estimates(estimator, count=5):
    """Create sample carbon estimates with varying parameters."""
    estimates = []

    base_time = datetime(2024, 1, 1, 9, 0, 0)

    for i in range(count):
        # Vary energy consumption and time
        energy_wh = 500.0 * (i + 1)  # 500Wh to 2500Wh
        start_time = base_time + timedelta(hours=i * 2)
        end_time = start_time + timedelta(hours=1)

        estimate = estimator.estimate_over_span(
            start_ts=start_time,
            end_ts=end_time,
            energy_wh=energy_wh,
            return_dataclass=False,  # Use dict format for ledger
        )

        estimates.append((estimate, f"operation_{i + 1}"))

    return estimates


def demonstrate_ledger_operations():
    """Demonstrate ledger creation, appending, and validation."""
    print("Carbon Ledger Operations Example")
    print("=" * 40)

    # Setup
    estimator = CarbonEstimator(region="us-west")
    signer = Signer(bytes(range(32)))

    with Path("carbon_ledger.ndjson").open("w") as f:
        f.write("")  # Create empty file

    ledger_path = Path("carbon_ledger.ndjson")

    # Create and append estimates
    print("Creating and appending carbon estimates...")
    estimates = create_sample_estimates(estimator, 3)

    for estimate, operation in estimates:
        signed_entry = append_carbon_estimate(
            ledger_path,
            estimate,
            signer,
            extra={"operation": operation, "version": "1.0"},
        )

        carbon_kg = estimate["carbon_emissions_gco2"] / 1000
        signature_preview = signed_entry.get("signature", "")[:16]
        print(
            f"Appended {operation}: {carbon_kg:.4f} kg CO2 (sig {signature_preview}...)"
        )

    # Validate ledger
    print("Validating ledger integrity...")
    is_valid, bad_line = validate_ledger(ledger_path, signer.signing_key)

    if is_valid:
        print("Ledger validation passed.")
    else:
        print(f"Ledger validation failed at line {bad_line}")
        return

    # Read and analyze ledger
    print("Analyzing ledger contents...")
    entries = []
    with ledger_path.open("r") as f:
        for line_num, line in enumerate(f, 1):
            try:
                entry = json.loads(line.strip())
                entries.append(entry)
                print(
                    f"Entry {line_num}: {entry.get('kind')} - "
                    f"{entry.get('carbon_emissions_gco2', 0):.2f}g CO2"
                )
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Failed to parse line {line_num}: {e}")
                continue

    # Calculate totals
    total_co2 = sum(
        e.get("carbon_emissions_gco2", 0)
        for e in entries
        if "carbon_emissions_gco2" in e
    )
    avg_co2_per_entry = total_co2 / len(entries) if entries else 0

    print(f"Total entries: {len(entries)}")
    print(f"Total CO2: {total_co2 / 1000:.4f} kg")
    print(f"Average emissions per entry: {avg_co2_per_entry:.2f} g CO2/entry")

    # Demonstrate signature verification
    print("Verifying signatures...")
    from carbon_ops.tools.verify import verify_json

    for i, entry in enumerate(entries, 1):
        ok, original = verify_json(entry, signer.signing_key)
        status = "Valid" if ok else "Invalid"
        print(f"Entry {i}: {status}")

    print(f"Ledger saved to: {ledger_path.absolute()}")


def demonstrate_concurrent_writes():
    """Demonstrate concurrent ledger writes (requires threading)."""
    print("Demonstrating concurrent ledger writes...")

    import threading

    estimator = CarbonEstimator()

    concurrent_ledger = Path("concurrent_ledger.ndjson")
    with concurrent_ledger.open("w") as f:
        f.write("")

    def worker_thread(thread_id, num_operations=3):
        """Worker function for concurrent writes."""
        thread_signer = Signer(bytes([thread_id] * 32))  # Different key per thread

        for i in range(num_operations):
            estimate = estimator.estimate_from_energy(100.0 * (i + 1))
            append_carbon_estimate(
                concurrent_ledger,
                estimate,
                thread_signer,
                extra={"thread": thread_id, "op_num": i + 1},
            )
            time.sleep(0.01)  # Small delay to encourage interleaving

    # Start concurrent threads
    threads = []
    num_threads = 3

    for t_id in range(num_threads):
        t = threading.Thread(target=worker_thread, args=(t_id,))
        threads.append(t)
        t.start()

    # Wait for completion
    for t in threads:
        t.join()

    # Validate concurrent ledger
    is_valid, bad_line = validate_ledger(
        concurrent_ledger, None
    )  # Don't check specific key
    if is_valid:
        print("Concurrent ledger validation passed.")

        # Count entries per thread
        thread_counts = {}
        with concurrent_ledger.open("r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    original = json.loads(entry.get("payload", "{}"))
                except (json.JSONDecodeError, TypeError) as exc:
                    print(f"Skipping malformed ledger entry: {exc}")
                    continue
                thread_id = original.get("thread", "unknown")
                thread_counts[thread_id] = thread_counts.get(thread_id, 0) + 1

        print("Entries per thread:")
        for thread_id, count in thread_counts.items():
            print(f"Thread {thread_id}: {count} entries")
    else:
        print(f"Concurrent ledger validation failed at line {bad_line}")

    print(f"Concurrent ledger saved to: {concurrent_ledger.absolute()}")


def cleanup_example_files():
    """Clean up example files."""
    files_to_remove = ["carbon_ledger.ndjson", "concurrent_ledger.ndjson"]

    for filename in files_to_remove:
        path = Path(filename)
        if path.exists():
            path.unlink()
            print(f"Removed {filename}")


def main():
    """Run the ledger operations example."""
    try:
        demonstrate_ledger_operations()
        demonstrate_concurrent_writes()

        print("Ledger operations example completed successfully.")
        print("Key takeaways:")
        print("- Ledger entries are cryptographically signed and chained")
        print("- Validation ensures data integrity and chronological order")
        print("- Concurrent writes are supported with proper locking")
        print("- Extra metadata can be attached to entries")
        print("- Use different signers for multi-tenant scenarios")

    except Exception as e:
        print(f"Example failed: {e}")
        raise
    finally:
        cleanup_example_files()


if __name__ == "__main__":
    main()
