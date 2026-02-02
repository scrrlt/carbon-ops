# Roadmap

This document records the currently planned work. It is updated when items are
completed or reprioritised.

## Short-term

- **Async intensity provider support:** add an `httpx.AsyncClient` transport and
  async-friendly estimator entry points.
- **Observability counters:** expose cache and latency metrics from the
  intensity provider layer.
- **Packaging cleanup:** continue reducing legacy dict returns and remove unused
  compatibility shims.

## Medium-term

- **Plugin interface:** allow external intensity providers to be discovered via
  entry points.
- **Governance guidance:** expand the deployment guide with baseline systemd
  unit recommendations and hardening checks.
- **Ledger tooling:** ship simple notebook utilities for inspecting ledger
  entries.

## Long-term

- **Reporting adapters:** integrate with external ESG and data catalog systems.
- **Workspace bundles:** determine whether to maintain a light reporting UI or
  ship a pre-configured notebook image.

Feedback on sequencing can be submitted through the issue tracker or by email
(s@scrrlt.dev).
