"""Configuration source utilities for :mod:`carbon_ops.config_loader`."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, TextIO, cast

from carbon_ops.settings import CarbonOpsSettings

_DEFAULT_CANDIDATES: tuple[Path, ...] = (
    Path("config/carbon.yml"),
    Path("configs/carbon.yml"),
    Path("config/carbon.json"),
    Path("configs/carbon.json"),
)


class YamlModule(Protocol):
    """Protocol describing the subset of PyYAML used by the loader."""

    def safe_load(self, stream: TextIO | str) -> object:
        """Parse YAML content from a text stream or string."""


def load_structured_config(
    path: str | None, settings: CarbonOpsSettings
) -> dict[str, object] | None:
    """Load configuration data from disk.

    Args:
        path: Explicit configuration path provided by the caller.
        settings: Environment-derived settings used for fallback discovery.

    Returns:
        A dictionary representation of the configuration file when discovered,
        otherwise ``None``.
    """

    candidates: Iterable[Path]
    if path is not None:
        candidates = (Path(path),)
    else:
        env_path = settings.carbon_config_path
        if env_path:
            candidates = (Path(env_path),)
        else:
            candidates = _DEFAULT_CANDIDATES

    for candidate in candidates:
        data = _load_config_file(candidate)
        if data is not None:
            return data
    return None


def _load_config_file(path: Path) -> dict[str, object] | None:
    """Load a configuration file based on suffix heuristics.

    Args:
        path: Candidate configuration path.

    Returns:
        Parsed mapping when the file exists and is readable, otherwise
        ``None``.
    """

    if not path.exists():
        return None
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix in {".yml", ".yaml"}:
        yaml_data = _load_yaml(path)
        if yaml_data is not None:
            return yaml_data
        return _load_json(path.with_suffix(".json"))
    return None


def _load_json(path: Path) -> dict[str, object] | None:
    """Load JSON configuration from ``path``.

    Args:
        path: JSON file path.

    Returns:
        Parsed mapping when the file is valid JSON, otherwise ``None``.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return _normalize_mapping(data)


def _load_yaml(path: Path) -> dict[str, object] | None:
    """Load YAML configuration from ``path`` when PyYAML is available.

    Args:
        path: YAML file path.

    Returns:
        Parsed mapping when the file is valid YAML, otherwise ``None``.
    """

    module = _import_yaml_module()
    if module is None:
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = module.safe_load(handle)
    except (OSError, UnicodeDecodeError):
        return None
    return _normalize_mapping(data)


def _import_yaml_module() -> YamlModule | None:
    """Import PyYAML lazily to avoid a hard dependency.

    Returns:
        The imported PyYAML module when available, otherwise ``None``.
    """

    try:
        import yaml
    except ModuleNotFoundError:
        return None
    return cast(YamlModule, yaml)


def _normalize_mapping(value: object) -> dict[str, object] | None:
    """Normalize potential mapping values to ``dict[str, object]``.

    Args:
        value: Arbitrary Python object produced by JSON/YAML parsing.

    Returns:
        Mapping restricted to string keys when possible, otherwise ``None``.
    """

    if not isinstance(value, dict):
        return None
    value_dict = cast(dict[object, object], value)
    normalized: dict[str, object] = {}
    for key_obj, item in value_dict.items():
        if not isinstance(key_obj, str):
            continue
        normalized[key_obj] = item
    return normalized
