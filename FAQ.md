# Frequently Asked Questions

## What does carbon-ops measure?

The library collects host energy metrics (CPU, GPU, memory, RAPL counters),
propagates them through the carbon estimation pipeline, and emits canonical
ledger records with hash chaining.

## Which Python versions are supported?

Python 3.10 and later. Tooling and CI use the versions pinned in
`pyproject.toml`.

## Do I need the governance daemon?

Use the daemon whenever accurate long-running RAPL sampling is required. It
polls at 10 Hz, maintains a 64-bit accumulator, and exposes the readings over a
Unix domain socket. The library falls back to monitor-only mode if the socket is
missing.

## How do sysfs and MSR modes differ?

Sysfs mode reads `/sys/class/powercap` energy files and works without elevated
privileges. MSR mode reads `/dev/cpu/<n>/msr`, looks up the energy unit via
MSR `0x606`, and requires root or `CAP_SYS_RAWIO`.

## What ledger format is used?

Ledger entries are newline-delimited canonical JSON documents. Each record
stores the hash of the previous entry (`prev_hash`) to provide simple tamper
detection.

## Is there an async API?

Not yet. Async support is listed in the roadmap. Current calls block while
fetching intensity data.

## How can I report issues or ask questions?

- Issues: [https://github.com/scrrlt/carbon-ops/issues](https://github.com/scrrlt/carbon-ops/issues)
- Discussions: GitHub Discussions coming soon
- Email: [s@scrrlt.dev](mailto:s@scrrlt.dev)
