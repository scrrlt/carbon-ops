"""Demonstrate RAPL aliasing when sampling below the Nyquist rate.

This script contrasts the dedicated carbon-governor daemon polling at 10 Hz
with a mock "Prometheus" scraper that only checks the counter every 15 seconds.
The slower sampler misses hardware wrap-around events that occur roughly every
14 seconds on 300 W CPUs/GPUs, leading to severe under-reporting.

Run on a Linux host with the msr kernel module loaded and sufficient
privileges:

    sudo python examples/aliasing_demo.py

The script will:
    1. Launch a busy CPU loop to consume power.
    2. Start the carbon-governor daemon (10 Hz sampling).
    3. Sample package energy through the governor client and a slow scraper.
    4. Compare measured energy after two minutes.

The output highlights the "11-second anomaly" where a 15-second scrape misses
at least one wrap-around event, proving that low-frequency collection is
unsafe.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from carbon_ops.governor.client import GovernorClient, GovernorUnavailableError

BUSY_LOOP_SLEEP = 0.0
PROM_SCRAPE_INTERVAL = 15.0
DEFAULT_DURATION = 120.0


@dataclass
class EnergyTotals:
    """Track cumulative energy deltas for comparison."""

    precise_uj: int = 0
    naive_uj: int = 0
    wraps_missed: int = 0


def _busy_loop(stop_event: threading.Event) -> None:
    """Consume CPU cycles to drive package power."""

    accumulator = 0
    while not stop_event.is_set():
        accumulator ^= 0xDEADBEEF
        accumulator = (accumulator << 1) & 0xFFFFFFFF
        if BUSY_LOOP_SLEEP:
            time.sleep(BUSY_LOOP_SLEEP)


def _start_daemon() -> subprocess.Popen[str]:
    """Launch the carbon governor daemon in the background."""

    cmd = [sys.executable, "-m", "carbon_ops.governor.daemon"]
    return subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


async def _collect_energy(duration: float) -> EnergyTotals:
    client = GovernorClient()
    start_snapshot = client.snapshot()
    totals = EnergyTotals()

    prom_totals: dict[str, int] = start_snapshot.counters_uj.copy()
    prom_accumulator: dict[str, int] = {name: 0 for name in prom_totals}

    start = time.monotonic()
    next_prom = start + PROM_SCRAPE_INTERVAL

    while time.monotonic() - start < duration:
        await asyncio.sleep(0.5)
        snapshot = client.snapshot()
        totals.precise_uj = sum(
            snapshot.counters_uj[name] - start_snapshot.counters_uj.get(name, 0)
            for name in snapshot.counters_uj
        )

        now = time.monotonic()
        if now >= next_prom:
            for name, value in snapshot.counters_uj.items():
                last = prom_totals.get(name, value)
                delta = value - last
                if delta < 0:
                    totals.wraps_missed += 1
                    delta = 0
                prom_accumulator[name] = prom_accumulator.get(name, 0) + delta
                prom_totals[name] = value
            totals.naive_uj = sum(prom_accumulator.values())
            next_prom += PROM_SCRAPE_INTERVAL

    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description="Demonstrate RAPL aliasing hazards")
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help="Experiment duration in seconds (default: 120)",
    )
    args = parser.parse_args()

    if os.name != "posix":
        print("This demo requires Linux with the msr module loaded.")
        return 1

    stop_event = threading.Event()
    worker = threading.Thread(target=_busy_loop, args=(stop_event,), daemon=True)
    worker.start()

    daemon_proc = _start_daemon()
    time.sleep(2.0)

    try:
        totals = asyncio.run(_collect_energy(args.duration))
    except GovernorUnavailableError as exc:
        print("Governor unavailable:", exc)
        print("Ensure the daemon is running with the required privileges.")
        totals = EnergyTotals()
    finally:
        stop_event.set()
        worker.join(timeout=1.0)
        if daemon_proc.poll() is None:
            try:
                os.kill(daemon_proc.pid, signal.SIGTERM)
            except OSError:
                pass
            daemon_proc.wait(timeout=5.0)

    print("=== Aliasing Demonstration ===")
    print(f"Duration: {args.duration:.1f} seconds")
    print(f"Governor energy (precise): {totals.precise_uj / 1e6:.3f} J")
    print(f"Mock Prometheus energy (15s scrape): {totals.naive_uj / 1e6:.3f} J")
    if totals.precise_uj > 0:
        loss_pct = (
            (1 - (totals.naive_uj / totals.precise_uj)) * 100
            if totals.precise_uj
            else 0
        )
        print(f"Energy lost due to aliasing: {loss_pct:.1f}%")
    print(f"Wrap-around events missed: {totals.wraps_missed}")
    print("(A non-zero miss count demonstrates the 11-second anomaly.)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
