"""Tests for telemetry configuration helpers."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from typing import cast
from dataclasses import dataclass

import pytest

from carbon_ops.telemetry import config


@pytest.fixture(autouse=True)
def _clear_cached_defaults() -> Iterator[None]:
    """Ensure cached defaults do not leak between tests."""

    config._cached_defaults.cache_clear()  # type: ignore[attr-defined]
    yield
    config._cached_defaults.cache_clear()  # type: ignore[attr-defined]


def test_resolve_cpu_tdp_watts_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variable should override defaults."""
    monkeypatch.setenv("CPU_TDP_WATTS", "123.45")
    assert math.isclose(config.resolve_cpu_tdp_watts(), 123.45)


def test_resolve_cpu_tdp_watts_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Packaged defaults are used when the environment is unset."""
    monkeypatch.delenv("CPU_TDP_WATTS", raising=False)

    def _default_payload() -> dict[str, object]:
        return {"CPU_TDP_WATTS": 95.5}

    monkeypatch.setattr(config, "_load_defaults_payload", _default_payload)
    assert math.isclose(config.resolve_cpu_tdp_watts(), 95.5)


def test_resolve_cpu_tdp_watts_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return fallback constant when no defaults are available."""
    monkeypatch.delenv("CPU_TDP_WATTS", raising=False)

    def _empty_payload() -> dict[str, object]:
        return {}

    monkeypatch.setattr(config, "_load_defaults_payload", _empty_payload)
    assert math.isclose(config.resolve_cpu_tdp_watts(), 85.0)


def test_resolve_cpu_tdp_watts_env_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid env values should defer to packaged defaults."""

    monkeypatch.setenv("CPU_TDP_WATTS", "invalid")

    def _defaults() -> dict[str, object]:
        return {"CPU_TDP_WATTS": 90.0}

    monkeypatch.setattr(config, "_load_defaults_payload", _defaults)
    assert math.isclose(config.resolve_cpu_tdp_watts(), 90.0)


@dataclass
class _ResourceStub:
    """Simple resource stub mimicking importlib.resources API."""

    text: str

    def joinpath(self, _: str) -> "_ResourceStub":
        return self

    def read_text(self, encoding: str) -> str:  # noqa: ARG002 - signature compatibility
        return self.text


def test_load_defaults_payload_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed JSON should result in an empty defaults mapping."""

    def _resource_loader(_: str) -> _ResourceStub:
        return _ResourceStub("not-json")

    monkeypatch.setattr(
        config.resources,
        "files",
        cast(Callable[[str], _ResourceStub], _resource_loader),
    )
    assert config._load_defaults_payload() == {}  # type: ignore[attr-defined]


def test_load_defaults_payload_non_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-dictionary payloads should be ignored."""

    class _ArrayResource(_ResourceStub):
        def read_text(self, encoding: str) -> str:  # noqa: ARG002
            return "[1, 2, 3]"

    def _array_loader(_: str) -> _ArrayResource:
        return _ArrayResource("[]")

    monkeypatch.setattr(
        config.resources, "files", cast(Callable[[str], _ArrayResource], _array_loader)
    )
    assert config._load_defaults_payload() == {}  # type: ignore[attr-defined]


def test_load_defaults_payload_missing_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing resource files should produce an empty defaults mapping."""

    def _missing_loader(_: str) -> None:
        raise FileNotFoundError("defaults missing")

    monkeypatch.setattr(config.resources, "files", _missing_loader)  # type: ignore[arg-type]
    assert config._load_defaults_payload() == {}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_resolve_cpu_tdp_watts_async(monkeypatch: pytest.MonkeyPatch) -> None:
    """Async resolver should delegate to the synchronous helper when cached."""

    monkeypatch.delenv("CPU_TDP_WATTS", raising=False)

    def _async_payload() -> dict[str, object]:
        return {"CPU_TDP_WATTS": 77}

    monkeypatch.setattr(config, "_load_defaults_payload", _async_payload)

    config._cached_defaults.cache_clear()  # type: ignore[attr-defined]
    result = await config.resolve_cpu_tdp_watts_async()
    assert math.isclose(result, 77.0)

    await config.resolve_cpu_tdp_watts_async()
    assert config._cached_defaults.cache_info().hits > 0  # type: ignore[attr-defined]
