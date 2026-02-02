"""Backward-compatible energy logging entry point."""

from __future__ import annotations

import builtins
import importlib
import sys
from types import ModuleType
from typing import cast

from carbon_ops.telemetry._psutil_protocols import PsutilProtocol
from carbon_ops.telemetry.logger import EnergyLogger as _TelemetryEnergyLogger

_cached_psutil = sys.modules.get("psutil")
if _cached_psutil is not None:
    sys.modules.pop("psutil", None)

try:  # pragma: no cover - psutil is required at runtime
    _psutil = builtins.__import__("psutil")
except (
    ModuleNotFoundError,
    ImportError,
) as exc:  # pragma: no cover - enforce dependency visibility
    if _cached_psutil is not None:
        sys.modules["psutil"] = _cached_psutil
    raise ImportError("psutil is required for carbon_ops.energy_logger") from exc

psutil = cast(PsutilProtocol, _psutil)

pynvml: ModuleType | None
try:  # pragma: no cover - optional dependency
    pynvml = importlib.import_module("pynvml")
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pynvml = None

EnergyLogger = _TelemetryEnergyLogger

__all__ = ["EnergyLogger", "psutil", "pynvml"]
