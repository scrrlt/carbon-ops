"""Public entry points for the :mod:`carbon_ops` configuration loader."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from carbon_ops.config_loader.models import (
    CarbonConfig,
    InterpolationSettings,
    LabelingSettings,
    MissingPolicy,
    PUEConfig,
    ProviderSettings,
    RegionSettings,
)
from carbon_ops.config_loader.parsing import (
    apply_environment_overrides,
    apply_structured_overrides,
)
from carbon_ops.config_loader.sources import load_structured_config
from carbon_ops.settings import CarbonOpsSettings, get_settings

__all__ = [
    "CarbonConfig",
    "InterpolationSettings",
    "LabelingSettings",
    "MissingPolicy",
    "PUEConfig",
    "ProviderSettings",
    "RegionSettings",
    "load_config",
]


def load_config(
    path: str | None = None, *, settings: CarbonOpsSettings | None = None
) -> CarbonConfig:
    """Load configuration from environment and optional file sources.

    Args:
        path: Optional explicit path to a configuration file. When omitted the
            loader inspects the environment and default search locations.
        settings: Optional pre-instantiated environment settings. When omitted
            :func:`carbon_ops.settings.get_settings` is used.

    Returns:
        Fully populated :class:`CarbonConfig` instance.
    """

    return _from_file(CarbonConfig, path, settings=settings)


def _from_env(
    cls: type[CarbonConfig], *, settings: CarbonOpsSettings | None = None
) -> CarbonConfig:
    """Build a configuration instance using environment overrides only."""

    env_settings = settings or get_settings()
    base = cls()
    return apply_environment_overrides(base, env_settings)


def _from_file(
    cls: type[CarbonConfig],
    path: str | None = None,
    *,
    settings: CarbonOpsSettings | None = None,
) -> CarbonConfig:
    """Build a configuration instance using environment and file overrides."""

    env_settings = settings or get_settings()
    base = apply_environment_overrides(cls(), env_settings)
    structured = load_structured_config(path, env_settings)
    if structured is None:
        return base
    return apply_structured_overrides(base, structured)


def _attach_classmethod(name: str, func: Callable[..., CarbonConfig]) -> None:
    """Attach ``func`` as a classmethod on :class:`CarbonConfig`."""

    setattr(CarbonConfig, name, classmethod(func))


def _bootstrap_classmethods() -> None:
    """Inject compatibility helpers onto :class:`CarbonConfig`."""

    _attach_classmethod("from_env", _from_env)
    _attach_classmethod("from_file", _from_file)


_bootstrap_classmethods()

if TYPE_CHECKING:  # pragma: no cover - typing helpers

    def _from_env_stub(
        cls: type[CarbonConfig], *, settings: CarbonOpsSettings | None = None
    ) -> CarbonConfig: ...

    def _from_file_stub(
        cls: type[CarbonConfig],
        path: str | None = None,
        *,
        settings: CarbonOpsSettings | None = None,
    ) -> CarbonConfig: ...

    CarbonConfig.from_env = classmethod(_from_env_stub)  # type: ignore[attr-defined]
    CarbonConfig.from_file = classmethod(_from_file_stub)  # type: ignore[attr-defined]
