"""CPU telemetry collection utilities."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import ModuleType
from typing import cast

from carbon_ops.types import CPUMetrics
from carbon_ops.telemetry.config import resolve_cpu_tdp_watts
from carbon_ops.telemetry._psutil_protocols import PsutilProtocol

_PSUTIL_MODULE: ModuleType = importlib.import_module("psutil")


def _default_psutil() -> PsutilProtocol:
    """Return the psutil module cast to the internal protocol."""

    return cast(PsutilProtocol, _PSUTIL_MODULE)


@dataclass(slots=True)
class CpuMetricsReader:
    """Collect CPU utilisation and estimated power metrics.

    Attributes:
        idle_power_ratio: Ratio used to estimate idle power draw relative to
            the CPU's thermal design power.
        power_gamma: Exponent applied to utilisation when estimating power.
        psutil_module: Injected psutil-compatible module for sampling metrics.
    """

    idle_power_ratio: float = 0.2
    power_gamma: float = 0.8
    psutil_module: PsutilProtocol = field(default_factory=_default_psutil, repr=False)
    _tdp_watts: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.psutil_module.cpu_percent(interval=None)
        self._tdp_watts = resolve_cpu_tdp_watts()

    def read(self) -> CPUMetrics:
        """Capture CPU utilisation and estimated power draw.

        Returns:
            Mapping containing utilisation percentage, frequency in megahertz,
            and estimated power consumption in watts.
        """
        cpu_percent = self.psutil_module.cpu_percent(interval=0.0)
        cpu_freq = self.psutil_module.cpu_freq()
        freq_current = (
            float(cpu_freq.current)
            if cpu_freq is not None and cpu_freq.current is not None
            else 0.0
        )

        idle_power = self.idle_power_ratio * self._tdp_watts
        utilisation_factor = (cpu_percent / 100.0) ** self.power_gamma
        estimated_power = (
            idle_power + (self._tdp_watts - idle_power) * utilisation_factor
        )

        return {
            "cpu_percent": float(cpu_percent),
            "cpu_freq_mhz": freq_current,
            "estimated_power_watts": float(estimated_power),
        }
