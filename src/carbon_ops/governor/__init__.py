"""Governance daemon primitives for hardware energy polling."""

from __future__ import annotations

from importlib import import_module
from typing import Any, TYPE_CHECKING

__all__ = [
    "GovernorClient",
    "GovernorRuntime",
    "GovernorSnapshot",
    "PollResult",
    "RaplDomain",
    "RaplTopology",
    "RaplTopologyConfig",
    "create_rapl_topology",
    "run_governor",
]

if TYPE_CHECKING:
    from .client import GovernorClient, GovernorSnapshot
    from .rapl import RaplDomain, RaplTopology, RaplTopologyConfig, create_rapl_topology
    from .runtime import GovernorRuntime, PollResult, run_governor


def __getattr__(name: str) -> Any:
    """Lazily resolve governance symbols to avoid optional dependencies."""

    module_map = {
        "GovernorClient": "client",
        "GovernorSnapshot": "client",
        "RaplDomain": "rapl",
        "RaplTopology": "rapl",
        "RaplTopologyConfig": "rapl",
        "create_rapl_topology": "rapl",
        "GovernorRuntime": "runtime",
        "PollResult": "runtime",
        "run_governor": "runtime",
    }

    if name not in module_map:
        raise AttributeError(name)

    module = import_module(f".{module_map[name]}", __name__)
    return getattr(module, name)
