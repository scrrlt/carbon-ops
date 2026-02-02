"""Tests for carbon intensity data loading."""

import importlib
import importlib.resources as ir
import json
import sys
import tempfile
from pathlib import Path
from carbon_ops.carbon_estimator import CarbonEstimator


def test_carbon_intensity_loaded_from_resource():
    """Test loading carbon intensity from resources."""
    regions = CarbonEstimator.get_available_regions()
    assert isinstance(regions, dict)
    assert "global-average" in regions
    assert regions["global-average"] > 0


def test_carbon_intensity_fallback(monkeypatch):
    """Test fallback when resource loading fails."""

    class Bad:
        def joinpath(self, *args, **kwargs):
            raise RuntimeError("no resource")

    original_module = sys.modules.get("carbon_ops.carbon_estimator")
    with monkeypatch.context() as mpatch:
        mpatch.setattr(ir, "files", lambda package: Bad())

        # Reload module to pick up monkeypatched behavior
        importlib.reload(importlib.import_module("carbon_ops.carbon_estimator"))
        ce = importlib.import_module("carbon_ops.carbon_estimator").CarbonEstimator
        regions = ce.get_available_regions()
        assert isinstance(regions, dict)
        assert "global-average" in regions

    if original_module is not None:
        importlib.reload(original_module)


def test_carbon_intensity_env_override(tmp_path, monkeypatch):
    """Test environment variable override for carbon intensity file."""
    # Write a small tmp JSON file and force the module to pick it up via env var
    data = {"global-average": 123.0, "us-east": 111}
    p = tmp_path / "override.json"
    p.write_text(__import__("json").dumps(data), encoding="utf-8")
    original_module = sys.modules.get("carbon_ops.carbon_estimator")
    with monkeypatch.context() as mpatch:
        mpatch.setenv("CARBON_OPS_CARBON_INTENSITY_FILE", str(p))

        # Reload module and assert values reflect override
        m = importlib.reload(importlib.import_module("carbon_ops.carbon_estimator"))
        regions = m.CarbonEstimator.get_available_regions()
        assert regions["global-average"] == 123.0
        assert regions["us-east"] == 111.0

    if original_module is not None:
        importlib.reload(original_module)


def test_carbon_intensity_env_override_legacy(monkeypatch):
    """Legacy ACS environment variable should remain supported."""

    original_module = sys.modules.get("carbon_ops.carbon_estimator")
    with monkeypatch.context() as mpatch:
        data = {
            "global-average": 555.0,
            "us-west": 444.0,
        }
        p = Path(tempfile.gettempdir()) / "legacy-carbon.json"
        p.write_text(json.dumps(data), encoding="utf-8")

        mpatch.setenv("ACSE_CARBON_INTENSITY_FILE", str(p))

        module = importlib.reload(
            importlib.import_module("carbon_ops.carbon_estimator")
        )
        regions = module.CarbonEstimator.get_available_regions()
        assert regions["global-average"] == 555.0
        assert regions["us-west"] == 444.0

    if original_module is not None:
        importlib.reload(original_module)
