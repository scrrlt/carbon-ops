"""Tests for the governance daemon RAPL utilities."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import os

import pytest

from carbon_ops.governor.rapl import (
    RaplDomain,
    RaplNotAvailableError,
    RaplReadError,
    RaplTopology,
    RaplTopologyConfig,
    create_rapl_topology,
)


class SequenceReader:
    """Return successive integer readings to emulate hardware."""

    def __init__(self, readings: deque[int]) -> None:
        if not readings:
            raise ValueError("SequenceReader requires at least one reading")
        self._readings = readings

    def __call__(self) -> int:
        value = self._readings[0]
        if len(self._readings) > 1:
            self._readings.popleft()
        return value


def test_rapl_domain_accumulates_delta() -> None:
    """Normal monotonic increases should be accumulated exactly."""

    reader = SequenceReader(deque([1_000, 1_250, 1_725, 2_000]))
    domain = RaplDomain(
        name="package-0:intel-rapl:0", max_energy_range_uj=10_000, reader=reader
    )

    assert domain.advance() == 250
    assert domain.advance() == 475
    assert domain.advance() == 275
    assert domain.total_energy_uj == 1_000
    assert domain.wrap_events == 0


def test_rapl_domain_handles_wraparound() -> None:
    """Wrap-around events must be compensated and tallied."""

    max_range = 2**32
    reader = SequenceReader(deque([max_range - 200, 120, 500]))
    domain = RaplDomain(
        name="package-0:intel-rapl:0", max_energy_range_uj=max_range, reader=reader
    )

    first_delta = domain.advance()
    assert first_delta == 320
    assert domain.wrap_events == 1

    second_delta = domain.advance()
    assert second_delta == 380
    assert domain.total_energy_uj == first_delta + second_delta


def test_rapl_domain_discards_implausible_jump(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Jumps larger than the threshold should be ignored and logged."""

    reader = SequenceReader(deque([1_000, 9_000]))
    domain = RaplDomain(
        name="package-0:intel-rapl:0",
        max_energy_range_uj=10_000,
        reader=reader,
        wrap_threshold_ratio=0.25,
    )

    caplog.set_level("WARNING")
    delta = domain.advance()
    assert delta == 0
    assert domain.total_energy_uj == 0
    assert caplog.records
    assert "invalid delta" in caplog.records[0].message.lower()


@pytest.mark.skipif(os.name != "posix", reason="Requires POSIX-style path semantics")
def test_create_rapl_topology_discovers_domains(tmp_path: Path) -> None:
    """Topology discovery should read sysfs-style directories."""

    base = tmp_path / "powercap"
    domain_dir = base / "intel-rapl:0"
    domain_dir.mkdir(parents=True)

    (domain_dir / "name").write_text("package-0", encoding="utf-8")
    (domain_dir / "energy_uj").write_text("12345", encoding="utf-8")
    (domain_dir / "max_energy_range_uj").write_text(str(2**32), encoding="utf-8")

    topology = create_rapl_topology(RaplTopologyConfig(base_path=base, recurse=False))
    assert isinstance(topology, RaplTopology)
    snapshot = topology.snapshot()
    assert "package-0:intel-rapl:0" in snapshot
    assert snapshot["package-0:intel-rapl:0"] == 0


def test_create_rapl_topology_requires_base_path(tmp_path: Path) -> None:
    """Missing sysfs paths should raise RaplNotAvailableError."""

    base = tmp_path / "missing"
    config = RaplTopologyConfig(base_path=base)
    with pytest.raises(RaplNotAvailableError):
        create_rapl_topology(config)


@pytest.mark.skipif(os.name != "posix", reason="Requires POSIX-style path semantics")
def test_read_int_file_raises_on_non_numeric(tmp_path: Path) -> None:
    """Non-integer content should raise RaplReadError."""

    base = tmp_path / "powercap"
    domain_dir = base / "intel-rapl:0"
    domain_dir.mkdir(parents=True)

    (domain_dir / "name").write_text("package-0", encoding="utf-8")
    (domain_dir / "energy_uj").write_text("not-a-number", encoding="utf-8")

    config = RaplTopologyConfig(base_path=base, recurse=False)
    with pytest.raises(RaplReadError):
        create_rapl_topology(config)


def test_create_rapl_topology_msr(monkeypatch: pytest.MonkeyPatch) -> None:
    """MSR discovery should honour masked values and energy units."""

    import carbon_ops.governor.rapl as rapl

    energy_iter = iter([1, 3])

    def fake_read_msr(cpu: int, register: int) -> int:
        if register == rapl.MSR_RAPL_POWER_UNIT:
            # In the RAPL MSR, the energy unit is 1 / 2**energy_bits Joules.
            # Choosing energy_bits = 0 makes the unit exactly 1 Joule, which
            # `_energy_unit_microjoules` converts to 1_000_000 microjoules.
            return 0
        if register == rapl.MSR_PKG_ENERGY_STATUS:
            return next(energy_iter)
        raise AssertionError(f"Unexpected MSR register: {register}")

    monkeypatch.setattr(rapl, "_read_msr", fake_read_msr)
    monkeypatch.setattr(rapl, "_discover_online_cpus", lambda: [0])

    topology = create_rapl_topology(
        RaplTopologyConfig(mode="msr", wrap_threshold_ratio=1.0)
    )
    deltas = topology.tick()
    domain_name = next(iter(deltas))
    assert domain_name == "package-0:msr"
    assert deltas[domain_name] == 2_000_000
    assert topology.snapshot()[domain_name] == 2_000_000
