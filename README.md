# carbon-ops

`carbon-ops` provides tooling for measuring host energy use, estimating carbon
emissions, and writing canonical ledger records. The repository contains the
Python library, a privileged polling daemon, and helper scripts for audit
workflows.

## Components

- **Library:** energy logging helpers, carbon-estimation routines, and ledger
  utilities that emit canonical JSON lines with hash chaining.
- **Governance daemon:** polls RAPL counters at 10 Hz, maintains a monotonic
  accumulator, and serves readings over a Unix domain socket so unprivileged
  processes have access to wrap-safe totals.
- **Examples:** reference scripts that show how to assemble the pieces,
  including the aliasing demo that compares the governance daemon to a 15 s
  Prometheus-style scraper.
- **Documentation:** Markdown files and notes that cover deployment, limitations,
  and planned work.

## Use cases

- Collect host telemetry (CPU, GPU, memory, RAPL) for training or inference
  jobs and store the results as time-stamped metrics.
- Estimate carbon emissions for a completed span using location-aware grid
  intensity data. The estimator records the method (`analytical_truncated` or
  `monte_carlo`) and confidence interval metadata in the output.
- Append audit ledger entries where each JSON object includes the hash of
  the previous entry, enabling tamper detection.
- Attribute package-level energy to individual processes by combining
  governance-daemon readings with per-process CPU time (`allocation_ratio`).

## Installation

The project targets Python 3.10 and later on Linux hosts. RAPL-based telemetry
requires access to `/sys/class/powercap` or `/dev/cpu/*/msr` (kernel modules
`intel_rapl_common` and `msr`). Install with all extras to enable testing and
optional providers.

```bash
python -m pip install carbon-ops[all,dev]
```

Local development clones can use the supplied virtual environment helpers in
`scripts/` or standard tooling such as `pip` and `venv`.

## Quick start

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

If the governance daemon is not available, the energy summary will report
`attribution_mode="monitor_only"` and execution continues without raising
exceptions.

## Telemetry modes

Two RAPL backends are available:

- **Sysfs mode** (default): reads `/sys/class/powercap/.../energy_uj` files. All
  samples are masked to 32 bits before they are accumulated to prevent high-bit
  noise.
- **MSR mode** (privileged): reads `/dev/cpu/<n>/msr` directly. The governance
  daemon fetches MSR `0x606` (RAPL power unit register), applies a 32-bit mask to RAPL
  counters (for example MSR `0x611`), converts to microjoules, and maintains the
  same accumulator used by the sysfs path. Enable with
  `--rapl-mode=msr [--msr-cpus=…]`. Root or `CAP_SYS_RAWIO` and the `msr` kernel
  module are required.

## Governance daemon

Start the daemon with the default sysfs reader:

```bash
sudo python -m carbon_ops.governor.daemon
```

A minimal MSR launch targeting the first two sockets:

```bash
sudo python -m carbon_ops.governor.daemon --rapl-mode=msr --msr-cpus=0,1
```

The daemon listens on `/var/run/carbon-ops.sock` with `root:carbon-users`
ownership and `0o660` permissions. The library degrades to monitor-only mode if
the socket is unavailable.

## Aliasing demonstration

`examples/aliasing_demo.py` contrasts the 10 Hz governance-daemon output with a mock
Prometheus scraper that polls every 15 seconds. The script exercises a CPU busy
loop, records energy via the Unix socket, and reports the energy that the slow
scraper misses when RAPL wraps (the “11-second anomaly”).

```bash
sudo python examples/aliasing_demo.py --duration 120
```

## Ledger output

Ledger entries are written as canonical JSON lines. Each record includes the
previous entry hash (`prev_hash`), producing a simple hash chain for tamper
resistance. The ledger functions guarantee atomic writes using a temporary file
followed by `os.replace`.

## Testing

Run the test matrix after installing the development dependencies:

```bash
python -m pytest
python -m ruff check .
python -m black --check .
python -m mypy --strict .
python -m bandit -r src
```

The `pyproject.toml` file contains the exact tool versions used in CI.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Licensed under the terms of [LICENSE](LICENSE).

## Support

- Issues: https://github.com/scrrlt/carbon-ops/issues
- Discussions: https://github.com/scrrlt/carbon-ops/discussions
- Email: s@scrrlt.dev
