"""Carbon Operations - Energy and Carbon Tracking for AI Operations."""

from __future__ import annotations

from importlib import import_module
from typing import TypeVar, overload, TYPE_CHECKING

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

# Type-safe module attribute access using overloads
@overload
def __getattr__(name: "CarbonEstimator") -> type[CarbonEstimator]: ...

@overload  
def __getattr__(name: "EnergyLogger") -> type[EnergyLogger]: ...

@overload
def __getattr__(name: "CarbonTaxonomyLogger") -> type[CarbonTaxonomyLogger]: ...

@overload
def __getattr__(name: "AuditRecord") -> type[AuditRecord]: ...

@overload
def __getattr__(name: "CarbonEstimateDict") -> type[CarbonEstimateDict]: ...

def __getattr__(name: str) -> type:
    """Lazily import heavy modules to avoid eager dependency loading.
    
    Args:
        name: The module attribute name to import.
        
    Returns:
        The imported class type.
        
    Raises:
        AttributeError: If the requested module attribute doesn't exist.
    """

    module_map = {
        "CarbonEstimator": "carbon_estimator",
        "EnergyLogger": "energy_logger", 
        "CarbonTaxonomyLogger": "carbon_taxonomy",
        "AuditRecord": "schemas",
        "CarbonEstimateDict": "carbon_models",
    }

    if name not in module_map:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

    module = import_module(f".{module_map[name]}", __name__)
    return getattr(module, name)
