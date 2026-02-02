"""Tests for the RAPL energy reader abstraction."""

from __future__ import annotations

from pathlib import Path

import math

from carbon_ops.telemetry.rapl import RaplDomain, RaplReader


def test_rapl_reader_discovers_domains(tmp_path: Path) -> None:
    """RaplReader should detect energy domains and sum their values."""
    root = tmp_path / "intel-rapl"
    root.mkdir()

    package_domain = root / "intel-rapl_0"
    package_domain.mkdir()
    (package_domain / "energy_uj").write_text("1000", encoding="utf-8")
    (package_domain / "name").write_text("package-0", encoding="utf-8")

    dram_domain = root / "intel-rapl_0_0"
    dram_domain.mkdir()
    (dram_domain / "energy_uj").write_text("250", encoding="utf-8")

    reader = RaplReader(base_path=root)

    assert reader.is_available is True
    assert len(reader.domains) == 2
    total_energy = reader.read_total_energy_uj()
    assert total_energy == 1250.0


def test_rapl_domain_handles_read_errors(tmp_path: Path) -> None:
    """RaplDomain should fail gracefully when files are missing."""
    domain_path = tmp_path / "intel-rapl_1"
    domain_path.mkdir()
    (domain_path / "energy_uj").write_text("not-a-number", encoding="utf-8")

    domain = RaplDomain(energy_path=domain_path / "energy_uj", name="package-1")
    assert math.isnan(domain.read_energy_uj())


def test_rapl_domain_recovers_after_error(tmp_path: Path) -> None:
    """A domain should report valid energy once the counter file is corrected."""
    domain_path = tmp_path / "intel-rapl_2"
    domain_path.mkdir()
    energy_file = domain_path / "energy_uj"
    energy_file.write_text("not-a-number", encoding="utf-8")

    domain = RaplDomain(energy_path=energy_file, name="package-2")
    assert math.isnan(domain.read_energy_uj())

    energy_file.write_text("2048", encoding="utf-8")
    assert domain.read_energy_uj() == 2048.0


def test_rapl_reader_without_domains(tmp_path: Path) -> None:
    """RaplReader should report unavailable when no domains exist."""

    reader = RaplReader(base_path=tmp_path / "missing")
    assert reader.is_available is False
    assert reader.read_total_energy_uj() == 0.0


def test_rapl_reader_total_returns_nan_on_failed_domain(tmp_path: Path) -> None:
    """If any domain read fails the total should be NaN."""

    root = tmp_path / "intel-rapl"
    root.mkdir()
    domain_dir = root / "intel-rapl_0"
    domain_dir.mkdir()
    (domain_dir / "energy_uj").write_text("not-a-number", encoding="utf-8")

    reader = RaplReader(base_path=root)
    assert reader.is_available is True
    assert math.isnan(reader.read_total_energy_uj())
