# carbon-ops

`carbon-ops` is an application performance monitor (APM) for energy logging and carbon estimation in Python workloads. It measures marginal carbon emissions for individual tasks, tracks CPU, GPU, and memory usage, and propagates uncertainty through each estimate. Output is written as canonical JSON lines with hash chaining for auditability. The repository includes the core Python library, a privileged polling daemon, and supporting scripts for audit workflows.

## Components

- **Library**: Energy logging utilities, carbon estimation methods, and ledger emitters that produce tamper-evident records.
- **Governance daemon**: Polls RAPL counters at 10 Hz, maintains a monotonic accumulator, and exposes readings over a Unix domain socket for unprivileged access.
- **Examples**: Reference scripts demonstrating integration patterns, including a comparison between the governance daemon and a 15-second Prometheus-style scraper.
- **Documentation**: Markdown files covering deployment, telemetry modes, limitations, and planned features.

## Use Cases

- Collect host-level telemetry (CPU, GPU, memory, RAPL) for training or inference jobs.
- Estimate carbon emissions for a time span using location-specific grid intensity data. The estimator records the method (`analytical_truncated` or `monte_carlo`) and includes confidence interval metadata.
- Emit audit ledger entries with hash-linked JSON lines to support tamper detection.
- Attribute energy usage to individual processes using governance daemon totals and per-process CPU time (`allocation_ratio`).

## Installation

Supports Python 3.10 and later on Linux. RAPL-based telemetry requires access to `/sys/class/powercap` or `/dev/cpu/*/msr` (via `intel_rapl_common` and `msr` kernel modules). Install with extras to enable optional features and development tools:

```bash
python -m pip install carbon-ops[all,dev]
```

For local development, use the helpers in `scripts/` or standard tools like `venv` and `pip`.

## Quick Start

```python
from carbon_ops import CarbonEstimator, EnergyLogger

try:
    logger = EnergyLogger()
except Exception as exc:
    raise SystemExit(f"EnergyLogger initialisation failed: {exc}")

metric = logger.log_metrics("training_step")

estimator = CarbonEstimator()
record = estimator.estimate_over_span(
    start_ts=metric["timestamp_start"],
    end_ts=metric["timestamp_end"],
    energy_wh=metric["energy"]["energy_wh_total"],
)
print(record.to_dict())
```

If the governance daemon is unavailable, the logger reports `attribution_mode="monitor_only"` and continues execution without raising an exception.

## Telemetry Modes

Two RAPL backends are supported:

- **Sysfs mode** (default): Reads from `/sys/class/powercap/.../energy_uj`. Samples are masked to 32 bits before accumulation to reduce noise.
- **MSR mode** (privileged): Reads from `/dev/cpu/<n>/msr`. The daemon reads MSR `0x606` (power unit register), applies a 32-bit mask to counters (e.g., MSR `0x611`), converts to microjoules, and uses the same accumulator as sysfs. Enable with `--rapl-mode=msr [--msr-cpus=…]`. Requires root or `CAP_SYS_RAWIO` and the `msr` kernel module.

## Governance Daemon

Start the daemon using the default sysfs mode:

```bash
sudo python -m carbon_ops.governor.daemon
```

To use MSR mode on CPUs 0 and 1:

```bash
sudo python -m carbon_ops.governor.daemon --rapl-mode=msr --msr-cpus=0,1
```

The daemon listens on `/var/run/carbon-ops.sock` with `root:carbon-users` ownership and `0o660` permissions. If the socket is unavailable, the library falls back to monitor-only mode.

## Aliasing Demonstration

The script `examples/aliasing_demo.py` compares the 10 Hz governance daemon output with a simulated Prometheus scraper polling every 15 seconds. It runs a CPU-bound loop, logs energy via the Unix socket, and reports energy missed by the slower scraper due to RAPL counter wrapping.

```bash
sudo python examples/aliasing_demo.py --duration 120
```

## Ledger Output

Ledger entries are emitted as canonical JSON lines. Each entry includes the hash of the previous record (`prev_hash`) to form a hash chain. Writes are atomic, using a temporary file followed by `os.replace`.

## Testing

Run the test suite after installing development dependencies:

```bash
python -m pytest
python -m ruff check .
python -m black --check .
python -m mypy --strict .
python -m bandit -r src
```

Tool versions are pinned in `pyproject.toml` to match CI.

## Contributing

See [Contributing](./CONTRIBUTING). for contribution guidelines.

## License

This project is licensed under the terms of [MIT License](./LICENSE).

## Support

- Issues: [https://github.com/scrrlt/carbon-ops/issues](https://github.com/scrrlt/carbon-ops/issues)  
- Discussions: [https://github.com/scrrlt/carbon-ops/discussions](https://github.com/scrrlt/carbon-ops/discussions)  
- Email: s@scrrlt.dev
