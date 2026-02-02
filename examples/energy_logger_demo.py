"""Example script demonstrating EnergyLogger usage."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Iterable, Optional

from carbon_ops.energy_logger import EnergyLogger


def _synthetic_work(iterations: int) -> Iterable[int]:
    for i in range(iterations):
        _ = math.fsum(j * j for j in range(256))
        yield i


def _export_metrics(logger: EnergyLogger, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger.export_metrics(destination.as_posix())


def main(argv: Optional[list[str]] = None) -> int:
    """Demonstrate energy logging functionality."""
    parser = argparse.ArgumentParser(
        description=(
            "Collect a short burst of host metrics using the carbon-ops EnergyLogger and optionally export them."
        )
    )
    parser.add_argument("--operation", default="energy_logger_demo")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument(
        "--export", type=Path, help="Optional path for exporting metrics"
    )
    args = parser.parse_args(argv)

    energy_logger = EnergyLogger()
    for idx in _synthetic_work(max(args.iterations, 1)):
        energy_logger.log_metrics(
            operation=f"{args.operation}_iteration_{idx}",
            additional_info={"iteration": idx},
        )
        time.sleep(max(args.sleep, 0.0))

    summary = energy_logger.get_metrics_summary()
    print(json.dumps(summary, indent=2))

    if args.export is not None:
        _export_metrics(energy_logger, args.export)

    return 0


if __name__ == "__main__":  # pragma: no cover - example entry point
    raise SystemExit(main())
