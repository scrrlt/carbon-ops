"""Type definitions for carbon operations."""

from __future__ import annotations

from typing import TypedDict, List


class CPUMetrics(TypedDict):
    """Metrics for CPU usage and power estimation."""

    cpu_percent: float
    cpu_freq_mhz: float
    estimated_power_watts: float


class MemoryMetrics(TypedDict):
    """Metrics for memory usage."""

    memory_used_gb: float
    memory_percent: float
    memory_available_gb: float


class GPUMetrics(TypedDict, total=False):
    """Metrics for GPU usage and power."""

    gpu_id: int
    gpu_utilization_percent: int
    memory_utilization_percent: int
    memory_used_gb: float
    memory_total_gb: float
    power_watts: float


class EnergyMetric(TypedDict, total=False):
    """Complete energy metric record."""

    timestamp: str
    operation: str
    cpu: CPUMetrics
    memory: MemoryMetrics
    gpu: List[GPUMetrics]
    total_estimated_power_watts: float
    additional_info: dict[str, object] | None
    energy: dict[str, object] | None
