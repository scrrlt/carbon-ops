"""Reporting and equivalence helpers separate from core estimation."""

from __future__ import annotations


def compare_carbon_equivalents(carbon_kgco2: float) -> dict[str, str]:
    """Convert carbon emissions into human-friendly equivalents."""

    if carbon_kgco2 < 0:
        raise ValueError("carbon_kgco2 must be non-negative")
    return {
        "carbon_kgco2": f"{carbon_kgco2:.4f}",
        "equivalent_km_driven": f"{carbon_kgco2 / 0.12:.2f}",
        "equivalent_tree_days": f"{carbon_kgco2 / 0.021:.1f}",
        "equivalent_smartphone_charges": f"{carbon_kgco2 / 0.008:.0f}",
    }


def derive_rating(carbon_kg: float) -> str:
    """Derive an A+ to F rating based on total impact."""

    if carbon_kg < 0:
        raise ValueError("carbon_kg must be non-negative")
    if carbon_kg < 0.01:
        return "A+"
    if carbon_kg < 0.05:
        return "A"
    if carbon_kg < 0.1:
        return "B"
    if carbon_kg < 0.5:
        return "C"
    if carbon_kg < 1.0:
        return "D"
    if carbon_kg < 5.0:
        return "E"
    return "F"
