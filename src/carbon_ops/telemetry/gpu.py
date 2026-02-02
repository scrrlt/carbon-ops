"""GPU telemetry collection with optional NVIDIA NVML support."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Callable, Protocol, cast

from carbon_ops.types import GPUMetrics


class NvmlError(Exception):
    """Base NVML interaction error."""


class NvmlLibrary(Protocol):
    """Protocol describing the NVML functions used by the telemetry layer."""

    def nvmlInit(self) -> None:  # pragma: no cover - thin wrapper
        ...

    def nvmlShutdown(self) -> None:  # pragma: no cover - thin wrapper
        ...

    def nvmlDeviceGetCount(self) -> int: ...

    def nvmlDeviceGetHandleByIndex(self, index: int) -> object: ...

    def nvmlDeviceGetUtilizationRates(self, handle: object) -> "NvmlUtilisation": ...

    def nvmlDeviceGetMemoryInfo(self, handle: object) -> "NvmlMemoryInfo": ...

    def nvmlDeviceGetPowerUsage(self, handle: object) -> int: ...


class NvmlUtilisation(Protocol):
    """Protocol for NVML utilisation structures."""

    gpu: int
    memory: int


class NvmlMemoryInfo(Protocol):
    """Protocol for NVML memory information structures."""

    used: int
    total: int


def load_nvml_library() -> NvmlLibrary | None:
    """Attempt to import the NVML Python bindings."""
    try:
        module = import_module("pynvml")
    except ModuleNotFoundError:
        return None
    return cast(NvmlLibrary, module)


LogHandler = Callable[[str], None]


@dataclass(slots=True)
class GpuMetricsReader:
    """Collect GPU metrics via NVML when available."""

    on_warning: LogHandler | None = None
    nvml: NvmlLibrary | None = field(default=None, init=False, repr=False)
    gpu_count: int = field(default=0, init=False)
    _pending_warnings: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._pending_warnings = []
        library = load_nvml_library()
        if library is None:
            self.nvml = None
            return
        try:
            library.nvmlInit()
            count = library.nvmlDeviceGetCount()
        except Exception as exc:  # pragma: no cover - external library path
            self._warn(f"GPU monitoring unavailable: {exc}")
            self.nvml = None
            return
        self.nvml = library
        self.gpu_count = int(count)

    def read(self) -> list[GPUMetrics]:
        """Return GPU metrics for each detected device."""
        if self.nvml is None or self.gpu_count <= 0:
            return []

        metrics: list[GPUMetrics] = []
        for index in range(self.gpu_count):
            try:
                metrics.append(self._read_device(index))
            except Exception as exc:  # pragma: no cover - defensive path
                self._warn(f"Failed to read GPU metrics for index {index}: {exc}")
        return metrics

    def _read_device(self, index: int) -> GPUMetrics:
        if self.nvml is None:  # pragma: no cover - defensive guard
            raise NvmlError("NVML library not initialised")
        handle = self.nvml.nvmlDeviceGetHandleByIndex(index)
        utilisation = self.nvml.nvmlDeviceGetUtilizationRates(handle)
        memory_info = self.nvml.nvmlDeviceGetMemoryInfo(handle)
        try:
            power_mw = self.nvml.nvmlDeviceGetPowerUsage(handle)
        except Exception:  # pragma: no cover - defensive path
            power_mw = 0

        return {
            "gpu_id": index,
            "gpu_utilization_percent": int(getattr(utilisation, "gpu", 0)),
            "memory_utilization_percent": int(getattr(utilisation, "memory", 0)),
            "memory_used_gb": float(getattr(memory_info, "used", 0) / (1024**3)),
            "memory_total_gb": float(getattr(memory_info, "total", 0) / (1024**3)),
            "power_watts": float(power_mw) / 1000.0,
        }

    def shutdown(self) -> None:
        """Cleanly shutdown NVML when initialised."""
        if self.nvml is None:
            return
        try:
            self.nvml.nvmlShutdown()
        except Exception:  # pragma: no cover - defensive path
            self._warn("Failed to shutdown NVML cleanly")

    def _warn(self, message: str) -> None:
        if self.on_warning is None:
            self._pending_warnings.append(message)
            return
        self.on_warning(message)

    def register_warning_handler(self, handler: LogHandler) -> None:
        """Register a warning handler and replay buffered warnings."""
        self.on_warning = handler
        if not self._pending_warnings:
            return
        for message in self._pending_warnings:
            handler(message)
        self._pending_warnings.clear()
