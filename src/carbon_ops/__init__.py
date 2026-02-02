"""Carbon Operations - Energy and Carbon Tracking for AI Operations."""

from __future__ import annotations

from importlib import import_module
from typing import Any, TYPE_CHECKING

__all__ = [
    "CarbonEstimator",
    "EnergyLogger",
    "CarbonTaxonomyLogger",
    "AuditRecord",
    "CarbonEstimateDict",
]

if TYPE_CHECKING:
    from .carbon_estimator import CarbonEstimator
    from .carbon_models import CarbonEstimateDict
    from .carbon_taxonomy import CarbonTaxonomyLogger
    from .energy_logger import EnergyLogger
    from .schemas import AuditRecord


def __getattr__(name: str) -> Any:
    """Lazily import heavy modules to avoid eager dependency loading."""

    module_map = {
        "CarbonEstimator": "carbon_estimator",
        "EnergyLogger": "energy_logger",
        "CarbonTaxonomyLogger": "carbon_taxonomy",
        "AuditRecord": "schemas",
        "CarbonEstimateDict": "carbon_models",
    }

    if name not in module_map:
        raise AttributeError(name)

    module = import_module(f".{module_map[name]}", __name__)
    return getattr(module, name)
