"""Typed configuration dataclasses for :mod:`carbon_ops.config_loader`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MissingPolicy = Literal["step", "drop"]


@dataclass(slots=True)
class ProviderSettings:
    """Settings describing the intensity provider chain.

    Attributes:
        order: Ordered tuple of provider identifiers.
        ttl_seconds: Cache time-to-live applied to provider responses.
    """

    order: tuple[str, ...] = ()
    ttl_seconds: int = 300


@dataclass(slots=True)
class PUEConfig:
    """Power usage effectiveness configuration."""

    default: float = 0.0
    overrides: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class InterpolationSettings:
    """Configuration controlling interpolation behaviour."""

    bucket_minutes: int = 15
    missing_policy: MissingPolicy = "step"


@dataclass(slots=True)
class RegionSettings:
    """Configuration describing region defaults."""

    default: str = "global-average"


@dataclass(slots=True)
class LabelingSettings:
    """Controls for ledger labelling features."""

    emit_ledger_events: bool = False
    salt_env: str | None = "CHIMERA_SALT"


@dataclass(slots=True)
class CarbonConfig:
    """Strongly typed configuration container for carbon operations."""

    providers: ProviderSettings = field(default_factory=ProviderSettings)
    interpolation: InterpolationSettings = field(default_factory=InterpolationSettings)
    pue: PUEConfig = field(default_factory=PUEConfig)
    region: RegionSettings = field(default_factory=RegionSettings)
    labeling: LabelingSettings = field(default_factory=LabelingSettings)
