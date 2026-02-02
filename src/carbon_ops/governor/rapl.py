"""RAPL domain utilities for the carbon governor daemon.

This module encapsulates raw hardware polling so we can unit test wrap-around
behaviour and discovery logic without touching privileged sysfs paths.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Literal, cast

LOGGER = logging.getLogger(__name__)


class RaplError(RuntimeError):
    """Base class for RAPL polling errors."""


class RaplNotAvailableError(RaplError):
    """Raised when the system does not expose the RAPL filesystem."""


class RaplReadError(RaplError):
    """Raised when an individual RAPL file cannot be read."""


RawEnergyReader = Callable[[], int]

MSR_RAPL_POWER_UNIT = 0x606
MSR_PKG_ENERGY_STATUS = 0x611
MASK_32_BIT = (1 << 32) - 1


@dataclass(slots=True)
class RaplDomain:
    """Track a single RAPL energy domain with wrap-around compensation."""

    name: str
    max_energy_range_uj: int
    reader: RawEnergyReader
    wrap_threshold_ratio: float = 0.5
    logger: logging.Logger = field(default=LOGGER)
    _accumulated_uj: int = field(init=False, default=0)
    _last_raw_uj: int = field(init=False)
    _wrap_events: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.max_energy_range_uj <= 0:
            msg = (
                f"max_energy_range_uj must be positive, got {self.max_energy_range_uj}"
            )
            raise ValueError(msg)
        if not 0.0 < self.wrap_threshold_ratio <= 1.0:
            msg = "wrap_threshold_ratio must be within (0, 1]"
            raise ValueError(msg)
        try:
            initial = self.reader()
        except OSError as exc:  # pragma: no cover - hardware failure path
            raise RaplReadError(
                f"Failed to read initial energy for {self.name}"
            ) from exc
        if initial < 0:
            msg = f"Initial energy reading for {self.name} was negative: {initial}"
            raise RaplReadError(msg)
        self._last_raw_uj = initial

    @property
    def total_energy_uj(self) -> int:
        """Return the accumulated energy in microjoules."""

        return self._accumulated_uj

    @property
    def wrap_events(self) -> int:
        """Return the number of detected wrap events for diagnostics."""

        return self._wrap_events

    def advance(self) -> int:
        """Fetch the latest raw value and update the accumulator.

        Returns:
            The delta applied to the accumulator in microjoules. A value of zero
            indicates that the frame was dropped due to an invalid reading.

        Raises:
            RaplReadError: If the underlying energy reader fails.
        """

        try:
            current = self.reader()
        except OSError as exc:  # pragma: no cover - hardware failure path
            raise RaplReadError(f"Failed to read energy for {self.name}") from exc

        delta = current - self._last_raw_uj
        if delta < 0:
            delta += self.max_energy_range_uj
            self._wrap_events += 1
            self.logger.debug(
                "RAPL wrap detected",
                extra={"domain": self.name, "wrap_events": self._wrap_events},
            )

        # Guard against implausible jumps (for example, truncated reads).
        wrap_threshold = int(self.max_energy_range_uj * self.wrap_threshold_ratio)
        if delta < 0 or delta > wrap_threshold:
            self.logger.warning(
                "Discarded RAPL frame due to invalid delta",
                extra={
                    "domain": self.name,
                    "delta": delta,
                    "wrap_threshold": wrap_threshold,
                },
            )
            self._last_raw_uj = current
            return 0

        self._accumulated_uj += delta
        self._last_raw_uj = current
        return delta


@dataclass(slots=True)
class RaplTopologyConfig:
    """Configuration knobs for RAPL topology discovery."""

    base_path: Path = Path("/sys/class/powercap")
    energy_file: str = "energy_uj"
    name_file: str = "name"
    max_range_file: str = "max_energy_range_uj"
    recurse: bool = True
    wrap_threshold_ratio: float = 0.5
    mode: Literal["sysfs", "msr"] = "sysfs"
    msr_cpus: list[int] | None = None


@dataclass(slots=True)
class RaplTopology:
    """Collection of RAPL domains discovered on the host."""

    domains: dict[str, RaplDomain]

    def tick(self) -> dict[str, int]:
        """Advance all domains and return the latest deltas per domain.

        Returns:
            Mapping of domain identifiers to delta values in microjoules for
            the current polling interval.
        """

        deltas: dict[str, int] = {}
        for name, domain in self.domains.items():
            delta = domain.advance()
            deltas[name] = delta
        return deltas

    def snapshot(self) -> dict[str, int]:
        """Return the accumulated energy for each domain.

        Returns:
            Mapping of domain identifiers to cumulative microjoules since the
            domain was initialised.
        """

        return {name: domain.total_energy_uj for name, domain in self.domains.items()}


def _read_int_file(path: Path) -> int:
    """Return the integer stored in ``path``.

    Args:
        path: Sysfs file containing a numeric energy or range value.

    Returns:
        Integer parsed from the file contents.

    Raises:
        RaplReadError: If the file is missing, unreadable, or non-numeric.
    """

    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RaplReadError(f"Missing RAPL file: {path}") from exc
    except OSError as exc:  # pragma: no cover - filesystem error path
        raise RaplReadError(f"Failed to read RAPL file: {path}") from exc

    try:
        value = int(text, 10)
    except ValueError as exc:
        raise RaplReadError(f"Invalid integer in RAPL file {path}: {text!r}") from exc

    return _mask32(value)


def _iter_domain_dirs(config: RaplTopologyConfig) -> Iterable[Path]:
    """Yield directories that contain RAPL energy counters.

    Args:
        config: Discovery configuration controlling traversal behaviour.

    Yields:
        Paths pointing at directories with an ``energy_uj`` file.

    Raises:
        RaplNotAvailableError: If the configured base path does not exist.
    """

    if not config.base_path.exists():
        raise RaplNotAvailableError(
            f"RAPL base path does not exist: {config.base_path}"
        )

    if config.recurse:
        yield from (
            path.parent
            for path in config.base_path.glob(f"**/{config.energy_file}")
            if path.is_file()
        )
        return

    for candidate in config.base_path.iterdir():
        energy_path = candidate / config.energy_file
        if energy_path.is_file():
            yield candidate


def create_rapl_topology(config: RaplTopologyConfig | None = None) -> RaplTopology:
    """Discover and build RAPL domains for the current host.

    Args:
        config: Optional discovery configuration. Defaults to
            :class:`RaplTopologyConfig` with the canonical powercap path.

    Returns:
        A topology object capturing all discovered domains.

    Raises:
        RaplNotAvailableError: If no readable RAPL domains are found.
        RaplReadError: If mandatory files contain malformed content.
    """

    effective_config = config or RaplTopologyConfig()

    if effective_config.mode == "msr":
        domains = _create_msr_domains(effective_config)
    else:
        domains = _create_sysfs_domains(effective_config)

    if not domains:
        if effective_config.mode == "msr":
            raise RaplNotAvailableError(
                "No RAPL domains discovered via MSR interface. Ensure the 'msr' "
                "kernel module is loaded and the process has CAP_SYS_RAWIO."
            )
        raise RaplNotAvailableError(
            f"No RAPL domains discovered under {effective_config.base_path}"
        )

    return RaplTopology(domains=domains)


def _create_sysfs_domains(config: RaplTopologyConfig) -> dict[str, RaplDomain]:
    domains: dict[str, RaplDomain] = {}

    for domain_dir in _iter_domain_dirs(config):
        name_path = domain_dir / config.name_file
        energy_path = domain_dir / config.energy_file
        max_range_path = domain_dir / config.max_range_file

        try:
            domain_name = name_path.read_text(encoding="utf-8").strip()
            if not domain_name:
                raise ValueError("empty name")
        except (FileNotFoundError, ValueError):
            domain_name = domain_dir.name
            LOGGER.warning(
                "Falling back to directory name for unnamed RAPL domain",
                extra={"path": str(domain_dir)},
            )
        except OSError as exc:  # pragma: no cover - filesystem error path
            domain_name = domain_dir.name
            LOGGER.warning(
                "Failed to read domain name; using directory identifier",
                extra={"path": str(domain_dir)},
                exc_info=exc,
            )

        try:
            max_range = _read_int_file(max_range_path)
        except RaplReadError:
            LOGGER.warning(
                "Falling back to UINT32 max range for domain",
                extra={"domain": domain_name},
            )
            max_range = (2**32) - 1

        def _make_reader(path: Path) -> RawEnergyReader:
            def _reader() -> int:
                return _read_int_file(path)

            return _reader

        reader = _make_reader(energy_path)
        try:
            domain = RaplDomain(
                name=f"{domain_name}:{domain_dir.name}",
                max_energy_range_uj=max_range,
                reader=reader,
                wrap_threshold_ratio=config.wrap_threshold_ratio,
            )
        except RaplReadError:
            LOGGER.debug(
                "Failed to initialise RAPL domain",
                extra={"domain": domain_name, "path": str(energy_path)},
                exc_info=True,
            )
            raise

        domains[domain.name] = domain

    return domains


def _create_msr_domains(config: RaplTopologyConfig) -> dict[str, RaplDomain]:
    domains: dict[str, RaplDomain] = {}
    cpu_indices = config.msr_cpus or _discover_online_cpus()

    for cpu in cpu_indices:
        try:
            units_raw = _read_msr(cpu, MSR_RAPL_POWER_UNIT)
        except RaplReadError as exc:
            LOGGER.warning(
                "Failed to read RAPL power unit register",
                extra={"cpu": cpu},
                exc_info=exc,
            )
            continue

        energy_unit_microjoules = _energy_unit_microjoules(units_raw)
        max_range = max(int(round(MASK_32_BIT * energy_unit_microjoules)), 1)

        def _make_msr_reader(cpu_id: int, unit_microjoules: float) -> RawEnergyReader:
            def _reader() -> int:
                raw = _read_msr(cpu_id, MSR_PKG_ENERGY_STATUS)
                masked = _mask32(raw)
                microjoules = int(round(masked * unit_microjoules))
                return max(microjoules, 0)

            return _reader

        reader = _make_msr_reader(cpu, energy_unit_microjoules)

        domain = RaplDomain(
            name=f"package-{cpu}:msr",
            max_energy_range_uj=max_range,
            reader=reader,
            wrap_threshold_ratio=config.wrap_threshold_ratio,
        )
        domains[domain.name] = domain

    return domains


def _energy_unit_microjoules(units_raw: int) -> float:
    energy_bits = (units_raw >> 8) & 0x1F
    if energy_bits == 0:
        return 1_000_000.0
    joules = 1.0 / float(1 << energy_bits)
    return joules * 1_000_000.0


def _discover_online_cpus() -> list[int]:
    online_path = Path("/sys/devices/system/cpu/online")
    if not online_path.exists():
        return [0]

    text = online_path.read_text(encoding="utf-8").strip()
    indices: set[int] = set()
    for entry in text.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "-" in entry:
            start_str, end_str = entry.split("-", 1)
            start_idx = int(start_str)
            end_idx = int(end_str)
            indices.update(range(start_idx, end_idx + 1))
        else:
            indices.add(int(entry))
    return sorted(indices) or [0]


def _mask32(value: int) -> int:
    return value & MASK_32_BIT


def _read_msr(cpu: int, register: int) -> int:
    msr_path = Path(f"/dev/cpu/{cpu}/msr")
    try:
        with msr_path.open("rb") as msr_file:
            msr_file.seek(register)
            raw = msr_file.read(8)
    except FileNotFoundError as exc:
        raise RaplReadError(
            f"MSR device node not found at {msr_path}; is the 'msr' kernel module loaded?"
        ) from exc
    except PermissionError as exc:
        raise RaplReadError(
            "Permission denied reading MSR. Run as root or grant CAP_SYS_RAWIO."
        ) from exc
    except OSError as exc:  # pragma: no cover - device failure
        raise RaplReadError(
            f"I/O error reading MSR {hex(register)} on CPU {cpu}: {exc}"
        ) from exc

    if len(raw) != 8:
        raise RaplReadError(
            f"Short read while reading MSR {hex(register)} on CPU {cpu}: {len(raw)} bytes"
        )

    value = struct.unpack("Q", raw)[0]
    return cast(int, value)


__all__ = [
    "RaplDomain",
    "RaplError",
    "RaplNotAvailableError",
    "RaplReadError",
    "RaplTopology",
    "RaplTopologyConfig",
    "create_rapl_topology",
]
