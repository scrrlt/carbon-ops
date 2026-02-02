"""Protocols describing the subset of psutil used by telemetry."""

from __future__ import annotations

from typing import Protocol


class CpuFrequencyProtocol(Protocol):
    """Minimal interface for psutil CPU frequency responses."""

    current: float | None


class VirtualMemoryProtocol(Protocol):
    """Minimal interface for psutil virtual memory responses."""

    used: int
    percent: float
    available: int


class PsutilProtocol(Protocol):
    """Subset of psutil APIs used by telemetry modules."""

    def cpu_percent(self, interval: float | None = None) -> float:
        """Return CPU utilisation percentage."""

    def cpu_freq(self) -> CpuFrequencyProtocol | None:
        """Return CPU frequency information."""

    def virtual_memory(self) -> VirtualMemoryProtocol:
        """Return virtual memory statistics."""
