"""Telemetry subsystem for energy logging."""

from __future__ import annotations

from importlib import import_module
from typing import Any, TYPE_CHECKING

__all__ = ["EnergyLogger"]

if TYPE_CHECKING:
    from carbon_ops.telemetry.logger import EnergyLogger


def __getattr__(name: str) -> Any:
    """Lazily resolve telemetry helpers to avoid heavy imports at module load."""

    if name != "EnergyLogger":
        raise AttributeError(name)

    module = import_module("carbon_ops.telemetry.logger")
    return getattr(module, name)
