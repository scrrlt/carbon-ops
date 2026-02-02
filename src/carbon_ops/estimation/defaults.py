"""Default data loaders for carbon estimation.

The module centralises disk/resource access for default carbon intensity
and power usage effectiveness (PUE) values. Callers receive fully typed
mappings that can be cached by the import system.
"""

from __future__ import annotations

import json
import logging
import pathlib
from functools import lru_cache
from typing import Final

from carbon_ops.settings import get_settings

LOGGER = logging.getLogger(__name__)

_FALLBACK_INTENSITIES: Final[dict[str, float]] = {
    "us-east": 400.0,
    "us-west": 350.0,
    "us-central": 450.0,
    "eu-west": 300.0,
    "eu-north": 50.0,
    "asia-pacific": 600.0,
    "global-average": 475.0,
}

_FALLBACK_PUE_VALUES: Final[dict[str, float]] = {
    "cloud-hyperscale": 1.2,
    "enterprise": 1.6,
    "edge": 1.4,
    "on-premise": 1.8,
}


@lru_cache(maxsize=1)
def load_carbon_intensity_mapping() -> dict[str, float]:
    """Load the region → intensity mapping.

    Returns:
        Mapping of region identifiers to carbon intensity in gCO2/kWh.

    Raises:
        FileNotFoundError: Raised when the path specified via the
            ``CARBON_OPS_CARBON_INTENSITY_FILE`` (or legacy
            ``ACSE_CARBON_INTENSITY_FILE``) environment variable is missing.
        RuntimeError: Raised when the JSON content at the override path cannot
            be parsed.
    """
    settings = get_settings()
    override_path = settings.carbon_intensity_file
    if override_path:
        path = pathlib.Path(override_path)
        if not path.exists():
            msg = f"CARBON_OPS_CARBON_INTENSITY_FILE not found: {path}"
            raise FileNotFoundError(msg)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Failed to parse carbon intensity override JSON"
            ) from exc
        return {key: float(value) for key, value in data.items()}

    try:
        import importlib.resources as resources

        data_text = (
            resources.files("carbon_ops.data")
            .joinpath("carbon_intensity.json")
            .read_text(encoding="utf-8")
        )
        data = json.loads(data_text)
        return {key: float(value) for key, value in data.items()}
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.error("Failed to load packaged carbon intensity defaults: %s", exc)
        return dict(_FALLBACK_INTENSITIES)


@lru_cache(maxsize=1)
def load_pue_values() -> dict[str, float]:
    """Load the power usage effectiveness (PUE) defaults.

    Returns:
        Mapping of PUE profiles to numeric PUE values.
    """
    try:
        defaults_text = (
            pathlib.Path(__file__).resolve().parent.parent / "data" / "defaults.json"
        ).read_text(encoding="utf-8")
        defaults_data = json.loads(defaults_text)
        raw_values = defaults_data.get("PUE_VALUES", {})
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.error("Failed to load packaged PUE defaults: %s", exc)
        return dict(_FALLBACK_PUE_VALUES)

    if not isinstance(raw_values, dict):
        LOGGER.warning(
            "Unexpected PUE_VALUES payload type %s; using fallback defaults",
            type(raw_values),
        )
        return dict(_FALLBACK_PUE_VALUES)

    parsed: dict[str, float] = {}
    for key, value in raw_values.items():
        try:
            parsed[str(key)] = float(value)
        except (TypeError, ValueError):
            LOGGER.warning("Skipping invalid PUE override for key %s", key)
    return parsed or dict(_FALLBACK_PUE_VALUES)
