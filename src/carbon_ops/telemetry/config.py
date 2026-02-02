"""Telemetry configuration utilities for energy measurement defaults."""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from importlib import resources
from typing import Final

from carbon_ops.settings import get_settings

_DEFAULT_TDP_FALLBACK: Final[float] = 85.0


def _load_defaults_payload() -> dict[str, object]:
    """Load telemetry defaults from the packaged JSON resource.

    Returns:
        Dictionary containing default configuration values. The mapping is
        empty when the resource file is unavailable or malformed.
    """
    try:
        defaults_path = resources.files("carbon_ops.data").joinpath("defaults.json")
        data = defaults_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return {}

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}

    return {str(key): value for key, value in payload.items()}


@lru_cache(maxsize=1)
def _cached_defaults() -> dict[str, object]:
    """Return cached telemetry defaults."""
    return _load_defaults_payload()


def resolve_cpu_tdp_watts() -> float:
    """Resolve the CPU thermal design power (TDP) setting in watts.

    Resolution order: the ``CPU_TDP_WATTS`` environment variable (parsed via
    :class:`CarbonOpsSettings`), followed by packaged defaults, and finally a
    constant fallback when neither source is available.

    Returns:
        The CPU TDP value in watts.
    """
    settings = get_settings()
    env_value = settings.cpu_tdp_watts
    if env_value is not None:
        return env_value

    defaults = _cached_defaults()
    candidate = defaults.get("CPU_TDP_WATTS")
    if isinstance(candidate, (float, int)):
        return float(candidate)

    return _DEFAULT_TDP_FALLBACK


async def resolve_cpu_tdp_watts_async() -> float:
    """Resolve the CPU TDP setting without blocking the event loop.

    Returns:
        The CPU TDP value in watts.
    """
    if _cached_defaults.cache_info().currsize > 0:
        return resolve_cpu_tdp_watts()
    return await asyncio.to_thread(resolve_cpu_tdp_watts)
