"""Parsing and transformation helpers for :mod:`carbon_ops.config_loader`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from typing import cast

from carbon_ops.config_loader.models import CarbonConfig, MissingPolicy
from carbon_ops.settings import CarbonOpsSettings


def apply_environment_overrides(
    config: CarbonConfig, settings: CarbonOpsSettings
) -> CarbonConfig:
    """Apply environment-derived overrides to the configuration.

    Args:
        config: Base configuration instance.
        settings: Environment-derived settings.

    Returns:
        Configuration with environment overrides applied.
    """

    updated = config

    if settings.default_region:
        updated = replace(
            updated,
            region=replace(updated.region, default=settings.default_region),
        )

    if settings.bucket_minutes is not None:
        updated = replace(
            updated,
            interpolation=replace(
                updated.interpolation, bucket_minutes=settings.bucket_minutes
            ),
        )

    default_pue = settings.default_pue
    if isinstance(default_pue, (int, float)):
        updated = replace(
            updated,
            pue=replace(updated.pue, default=float(default_pue)),
        )
    elif isinstance(default_pue, str):
        numeric = _coerce_float(default_pue)
        if numeric is not None:
            updated = replace(updated, pue=replace(updated.pue, default=numeric))

    return updated


def apply_structured_overrides(
    config: CarbonConfig, data: Mapping[str, object]
) -> CarbonConfig:
    """Apply overrides sourced from structured configuration data.

    Args:
        config: Base configuration instance.
        data: Mapping parsed from configuration file.

    Returns:
        Configuration updated according to the provided mapping.
    """

    updated = config

    region_section = _expect_mapping(data.get("region"))
    if region_section is not None:
        updated = _apply_region_section(updated, region_section)

    pue_section = _expect_mapping(data.get("pue"))
    if pue_section is not None:
        updated = _apply_pue_section(updated, pue_section)

    interpolation_section = _expect_mapping(data.get("interpolation"))
    if interpolation_section is not None:
        updated = _apply_interpolation_section(updated, interpolation_section)

    providers_section = _expect_mapping(data.get("providers"))
    if providers_section is not None:
        updated = _apply_providers_section(updated, providers_section)

    labeling_section = _expect_mapping(data.get("labeling"))
    if labeling_section is not None:
        updated = _apply_labeling_section(updated, labeling_section)

    return updated


def _apply_region_section(
    config: CarbonConfig, section: Mapping[str, object]
) -> CarbonConfig:
    """Apply region-related overrides from a structured section.

    Args:
        config: Current configuration instance.
        section: Mapping describing the region section from the file.

    Returns:
        Updated configuration instance.
    """

    default_value = _coerce_str(section.get("default"))
    if default_value is None:
        return config
    return replace(config, region=replace(config.region, default=default_value))


def _apply_pue_section(
    config: CarbonConfig, section: Mapping[str, object]
) -> CarbonConfig:
    """Apply PUE overrides from a structured section.

    Args:
        config: Current configuration instance.
        section: Mapping describing the PUE section from the file.

    Returns:
        Updated configuration instance.
    """

    pue_config = config.pue

    default_value = _coerce_float(section.get("default"))
    if default_value is not None:
        pue_config = replace(pue_config, default=default_value)

    overrides_raw = section.get("overrides")
    if isinstance(overrides_raw, Mapping):
        overrides: dict[str, float] = {}
        for key, value in overrides_raw.items():
            key_str = _coerce_str(key)
            if key_str is None:
                continue
            value_float = _coerce_float(value)
            if value_float is None:
                continue
            overrides[key_str] = value_float
        if overrides:
            pue_config = replace(pue_config, overrides=dict(overrides))

    return replace(config, pue=pue_config)


def _apply_interpolation_section(
    config: CarbonConfig, section: Mapping[str, object]
) -> CarbonConfig:
    """Apply interpolation overrides from a structured section.

    Args:
        config: Current configuration instance.
        section: Mapping describing the interpolation section from the file.

    Returns:
        Updated configuration instance.
    """

    bucket_value = _coerce_int(section.get("bucket_minutes"))
    missing_policy = _coerce_missing_policy(section.get("missing_policy"))

    interpolation = config.interpolation
    if bucket_value is not None:
        interpolation = replace(interpolation, bucket_minutes=bucket_value)
    if missing_policy is not None:
        interpolation = replace(
            interpolation,
            missing_policy=cast(MissingPolicy, missing_policy),
        )
    return replace(config, interpolation=interpolation)


def _apply_providers_section(
    config: CarbonConfig, section: Mapping[str, object]
) -> CarbonConfig:
    """Apply intensity provider overrides from a structured section.

    Args:
        config: Current configuration instance.
        section: Mapping describing the providers section from the file.

    Returns:
        Updated configuration instance.
    """

    order_raw = section.get("order")
    order_values = _coerce_str_sequence(order_raw)
    ttl_value = _coerce_int(section.get("ttl_seconds"))

    providers = config.providers
    if order_values is not None:
        providers = replace(providers, order=order_values)
    if ttl_value is not None:
        providers = replace(providers, ttl_seconds=ttl_value)
    return replace(config, providers=providers)


def _apply_labeling_section(
    config: CarbonConfig, section: Mapping[str, object]
) -> CarbonConfig:
    """Apply labeling overrides from a structured section.

    Args:
        config: Current configuration instance.
        section: Mapping describing the labeling section from the file.

    Returns:
        Updated configuration instance.
    """

    emit_value = _coerce_bool(section.get("emit_ledger_events"))
    salt_value = _coerce_str(section.get("salt_env"))

    labeling = config.labeling
    if emit_value is not None:
        labeling = replace(labeling, emit_ledger_events=emit_value)
    if salt_value is not None:
        labeling = replace(labeling, salt_env=salt_value)
    return replace(config, labeling=labeling)


def _coerce_float(value: object) -> float | None:
    """Parse a float from arbitrary input.

    Args:
        value: Raw value.

    Returns:
        Parsed float when conversion succeeds, otherwise ``None``.
    """

    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    """Parse an integer from arbitrary input.

    Args:
        value: Raw value.

    Returns:
        Parsed integer when conversion succeeds, otherwise ``None``.
    """

    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _coerce_bool(value: object) -> bool | None:
    """Parse a boolean from arbitrary input.

    Args:
        value: Raw value.

    Returns:
        Parsed boolean when conversion succeeds, otherwise ``None``.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    if isinstance(value, (int, float)):
        if value == 0:
            return False
        if value == 1:
            return True
    return None


def _coerce_str(value: object) -> str | None:
    """Parse a string from arbitrary input.

    Args:
        value: Raw value.

    Returns:
        Normalised string when the input is textual, otherwise ``None``.
    """

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _coerce_str_sequence(value: object) -> tuple[str, ...] | None:
    """Parse a tuple of strings from an arbitrary iterable.

    Args:
        value: Raw iterable value.

    Returns:
        Tuple of strings when conversion succeeds, otherwise ``None``.
    """

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    items: list[str] = []
    for element in value:
        if not isinstance(element, str):
            return None
        items.append(element)
    return tuple(items)


def _coerce_missing_policy(value: object) -> str | None:
    """Parse a missing policy value.

    Args:
        value: Raw policy value.

    Returns:
        Sanitised policy string when valid, otherwise ``None``.
    """

    policy = _coerce_str(value)
    if policy in {"step", "drop"}:
        return policy
    return None


def _expect_mapping(value: object) -> Mapping[str, object] | None:
    """Return the value when it is a mapping with string keys.

    Args:
        value: Raw configuration value.

    Returns:
        Mapping with string keys suitable for further parsing, or ``None``.
    """

    if not isinstance(value, Mapping):
        return None
    if not all(isinstance(key, str) for key in value.keys()):
        return None
    return value
