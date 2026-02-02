# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/) and
follows the guidance of [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0a0] - Unreleased

### Added
- Energy telemetry pipeline with CPU, GPU, memory, and optional RAPL
  instrumentation.
- Carbon estimation workflow with uncertainty propagation, configurable
  intensity providers, and ledger JSON exports.
- Typed configuration loader supporting environment variable overrides and
  YAML/JSON inputs.
- Aggregation helpers for consolidating `CarbonEstimate` objects across regions
  or sources.
- Structured logging pipeline with queue-based handlers and JSON
  formatting.
- Pydantic audit schema enforcement with a companion JSON Schema export
  script for auditors.
- Cache instrumentation for intensity providers capturing cache hit/miss events
  with structured logging hooks.

### Changed
- Intensity provider error handling now surfaces structured warnings when
  external APIs fail or return invalid payloads, improving observability for
  prerelease users.
- Carbon estimator now composes a dedicated engine for provider orchestration
  while delegating reporting to focused modules, reducing change ripple.
- Legacy dict outputs are now backed by a `TypedDict`, providing a typed
  contract for downstream consumers during refactor.
- Historical telemetry modules now include Google-style docstrings for
  consistent project-wide documentation.

### Known Issues
- The `carbon_ops.estimation.estimator` module remains monolithic and will be
  split into dedicated components immediately after `0.1.0a0` ships.
- Public APIs still return legacy dictionaries in a few places; migrating to
  `TypedDict` surfaces is in progress.
- Schema export is manual; future releases will publish the generated artifact
  with tagged releases.
