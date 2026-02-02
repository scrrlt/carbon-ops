"""Deterministic carbon taxonomy calculations."""

from __future__ import annotations

from statistics import mean

THETA_OPERATIONAL_THRESHOLD: float = 0.15
THETA_MARGINAL_THRESHOLD: float = 0.30


def get_theta_regime(theta: float) -> str:
    """Classify the theta fraction into a descriptive regime string.

    Args:
        theta: Fraction of embodied emissions relative to total emissions.

    Returns:
        Regime identifier describing the dominant emissions component.
    """

    if theta < THETA_OPERATIONAL_THRESHOLD:
        return "operational_dominated"
    if theta < THETA_MARGINAL_THRESHOLD:
        return "marginal"
    return "embodied_dominated"


def compute_theta_fraction(operational_co2: float, embodied_co2: float) -> float:
    """Compute the embodied fraction of total carbon emissions.

    Args:
        operational_co2: Operational emissions in kilograms of CO₂e.
        embodied_co2: Embodied emissions in kilograms of CO₂e.

    Returns:
        Embodied emissions divided by the total emissions. Returns ``0.0`` when
        the total emissions are zero.
    """

    total_co2 = operational_co2 + embodied_co2
    return embodied_co2 / total_co2 if total_co2 > 0 else 0.0


def calculate_total_carbon(operational: float, embodied: float) -> float:
    """Calculate the total carbon emissions."""

    return operational + embodied


def calculate_carbon_intensity(energy_kwh: float, emissions_kg: float) -> float:
    """Calculate carbon intensity."""

    return emissions_kg / energy_kwh if energy_kwh > 0 else 0.0


def calculate_operational_emissions(energy_kwh: float, grid_intensity: float) -> float:
    """Calculate operational emissions based on energy and grid intensity."""

    return energy_kwh * grid_intensity / 1000.0


def calculate_energy(duration_hours: float, power_kw: float) -> float:
    """Calculate energy consumption in kilowatt hours."""

    return duration_hours * power_kw


def compute_carbon_offset(emissions: float, offset_rate: float) -> float:
    """Compute the carbon offset based on emissions and offset rate."""

    return emissions * offset_rate


def estimate_carbon_savings(
    current_emissions: float, optimized_emissions: float
) -> float:
    """Estimate carbon savings based on current and optimized emissions."""

    return current_emissions - optimized_emissions


def compare_emissions(emission_a: float, emission_b: float) -> str:
    """Compare two emission values and return the comparison result."""

    if emission_a > emission_b:
        return "higher"
    if emission_a < emission_b:
        return "lower"
    return "equal"


def summarize_emissions(emissions: list[float]) -> dict[str, float]:
    """Summarize a list of emissions with statistics."""

    if not emissions:
        return {"min": 0.0, "max": 0.0, "average": 0.0}
    return {
        "min": min(emissions),
        "max": max(emissions),
        "average": mean(emissions),
    }


def calculate_emission_ratio(emission_a: float, emission_b: float) -> float:
    """Calculate the ratio between two emission values."""

    return emission_a / emission_b if emission_b != 0 else 0.0


def normalize_emissions(emissions: list[float]) -> list[float]:
    """Normalize a list of emissions to a scale of 0 to 1."""

    if not emissions:
        return []
    max_emission = max(emissions)
    if max_emission == 0:
        return [0.0 for _ in emissions]
    return [emission / max_emission for emission in emissions]


def calculate_cumulative_emissions(emissions: list[float]) -> float:
    """Calculate the cumulative sum of emissions."""

    return sum(emissions)


def project_future_emissions(
    current_emissions: float, growth_rate: float, years: int
) -> float:
    """Project future emissions based on current emissions, growth rate, and years."""

    return current_emissions * ((1 + growth_rate) ** years)


def compute_emission_gap(target_emissions: float, actual_emissions: float) -> float:
    """Compute the gap between target and actual emissions."""

    return actual_emissions - target_emissions


def evaluate_emission_trend(emissions: list[float]) -> str:
    """Evaluate the trend of emissions over time."""

    if len(emissions) < 2:
        return "flat"
    increasing = all(
        emissions[i] <= emissions[i + 1] for i in range(len(emissions) - 1)
    )
    decreasing = all(
        emissions[i] >= emissions[i + 1] for i in range(len(emissions) - 1)
    )
    if increasing and not decreasing:
        return "increasing"
    if decreasing and not increasing:
        return "decreasing"
    return "fluctuating"


def calculate_average_emissions(emissions: list[float]) -> float:
    """Calculate the average emissions from a list."""

    return mean(emissions) if emissions else 0.0


def estimate_emissions_reduction(current: float, baseline: float) -> float:
    """Estimate the reduction in emissions compared to a baseline."""

    return baseline - current if baseline > current else 0.0
