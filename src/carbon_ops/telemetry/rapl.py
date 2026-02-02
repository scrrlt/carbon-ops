"""Intel RAPL energy reader."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("carbon_ops.telemetry.rapl")


@dataclass(slots=True)
class RaplDomain:
    """Representation of a single RAPL energy domain."""

    energy_path: Path
    name: str

    def read_energy_uj(self) -> float:
        """Read the current energy counter in microjoules.

        Returns:
            Energy reading in microjoules, or ``NaN`` if the domain cannot be
            read.
        """
        try:
            text = self.energy_path.read_text(encoding="utf-8").strip()
            return float(int(text))
        except (OSError, ValueError) as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "Failed to read RAPL domain %s at %s: %s",
                self.name,
                self.energy_path,
                exc,
            )
            return math.nan


@dataclass(slots=True)
class RaplReader:
    """Discover and read Intel RAPL domains when available."""

    base_path: Path = Path("/sys/class/powercap/intel-rapl")
    domains: list[RaplDomain] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.domains = list(self._discover_domains())

    def _discover_domains(self) -> Iterable[RaplDomain]:
        """Discover available RAPL domains under the configured base path."""

        if not self.base_path.exists():
            return []
        discovered: list[RaplDomain] = []
        for entry in self.base_path.iterdir():
            if not entry.is_dir():
                continue
            energy_file = entry / "energy_uj"
            if not energy_file.exists():
                continue
            name_file = entry / "name"
            name = (
                name_file.read_text(encoding="utf-8").strip()
                if name_file.exists()
                else entry.name
            )
            discovered.append(RaplDomain(energy_path=energy_file, name=name))
        return discovered

    @property
    def is_available(self) -> bool:
        """Indicate whether any RAPL domain is available."""
        return bool(self.domains)

    def read_total_energy_uj(self) -> float:
        """Read the sum of all discovered RAPL domains in microjoules.

        Returns:
            Sum of energy readings across domains, or ``NaN`` if any domain
            read fails.
        """
        if not self.domains:
            return 0.0

        total = 0.0
        for domain in self.domains:
            reading = domain.read_energy_uj()
            if math.isnan(reading):
                return math.nan
            total += reading
        return total
