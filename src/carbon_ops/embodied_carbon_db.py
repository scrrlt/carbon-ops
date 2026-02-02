"""Embodied Carbon Database for Carbon Taxonomy Research."""

from typing import Dict
from dataclasses import dataclass


@dataclass
class DeviceEmbodiedData:
    """Embodied carbon data for a device."""

    total_kg_co2e: float
    amortization_days: int
    source: str
    confidence: str

    def __post_init__(self) -> None:
        if self.amortization_days <= 0:
            raise ValueError("amortization_days must be a positive integer")

    @property
    def kg_per_day(self) -> float:
        """Calculate embodied carbon amortized per day."""
        return self.total_kg_co2e / self.amortization_days


EMBODIED_CARBON_DB: Dict[str, Dict[str, DeviceEmbodiedData]] = {
    "cloud_vm": {
        "cpu_only": DeviceEmbodiedData(200.0, 1825, "Masanet et al. 2020", "high"),
        "gpu_a100": DeviceEmbodiedData(800.0, 1095, "Vendor estimate", "medium"),
    },
    "edge": {
        "raspberry_pi_4": DeviceEmbodiedData(
            8.0, 1095, "Raspberry Pi Foundation", "high"
        ),
    },
    "mobile": {
        "smartphone_flagship": DeviceEmbodiedData(85.0, 730, "Vendor report", "high"),
    },
    "iot": {
        "sensor_node_battery": DeviceEmbodiedData(
            3.0, 1825, "Andrae & Edler 2015", "medium"
        ),
    },
}


def get_embodied_carbon(
    device_type: str, device_subtype: str
) -> DeviceEmbodiedData | None:
    """Retrieve embodied carbon data for a device."""
    if device_type not in EMBODIED_CARBON_DB:
        return None
    return EMBODIED_CARBON_DB[device_type].get(device_subtype)


def calculate_embodied_for_operation(
    device_type: str, device_subtype: str, duration_seconds: float
) -> Dict[str, object]:
    """Calculate embodied carbon for an operation duration."""
    data = get_embodied_carbon(device_type, device_subtype)
    if data is None:
        return {
            "embodied_kg": 0.0,
            "total_lifetime_kg": 0.0,
            "amortization_days": 0,
            "confidence": "none",
            "source": "missing",
        }
    embodied_per_second = data.kg_per_day / 86400.0
    embodied_operation = embodied_per_second * duration_seconds
    return {
        "embodied_kg": embodied_operation,
        "total_lifetime_kg": data.total_kg_co2e,
        "amortization_days": data.amortization_days,
        "confidence": data.confidence,
        "source": data.source,
    }
