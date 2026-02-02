"""Memory telemetry collection utilities."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import ModuleType
from typing import cast

from carbon_ops.types import MemoryMetrics
from carbon_ops.telemetry._psutil_protocols import PsutilProtocol

_PSUTIL_MODULE: ModuleType = importlib.import_module("psutil")


def _default_psutil() -> PsutilProtocol:
    """Return the psutil module cast to the internal protocol."""

    return cast(PsutilProtocol, _PSUTIL_MODULE)


@dataclass(slots=True)
class MemoryMetricsReader:
    """Collect memory utilisation metrics with an injectable psutil module."""

    psutil_module: PsutilProtocol = field(default_factory=_default_psutil, repr=False)

    def read(self) -> MemoryMetrics:
        """Collect memory utilisation metrics using psutil.

        Returns:
            Mapping containing used memory, available memory, and utilisation
            percentage.
        """
        memory = self.psutil_module.virtual_memory()
        return {
            "memory_used_gb": float(memory.used / (1024**3)),
            "memory_percent": float(memory.percent),
            "memory_available_gb": float(memory.available / (1024**3)),
        }


def read_memory_metrics() -> MemoryMetrics:
    """Return memory metrics using the default reader."""
    return MemoryMetricsReader().read()
