# Known Issues

This document lists outstanding gaps that require follow-up work.

## 1. Async intensity providers

- **Status:** Open
- **Details:** All grid intensity providers run synchronously. Calls that reach
  external services block the event loop when used in async applications.
- **Planned fix:** Implement an `httpx.AsyncClient` transport and expose async
  estimation helpers.

## 2. Telemetry observability

- **Status:** Open
- **Details:** Cache hit ratios and latency distributions collected inside the
  intensity provider layer are not yet exported via the public API or metrics
  hooks.
- **Planned fix:** Add structured counters, expose them through the logging
  pipeline, and optionally surface a Prometheus endpoint.

## 3. Reporting surface

- **Status:** Open
- **Details:** The project does not ship notebook templates or a lightweight UI
  for exploring ledger data.
- **Planned fix:** Decide between a simple notebook kit and an optional web
  frontend. Work is tracked in the roadmap under the “UI tooling” item.

---

Questions about these items can be directed to s@scrrlt.dev.
