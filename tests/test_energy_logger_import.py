"""Tests for energy logger imports and functionality."""

import builtins
import importlib
import json
import sys
from pathlib import Path

import pytest

from carbon_ops.energy_logger import EnergyLogger


def test_export_metrics(tmp_path: Path):
    """Test exporting metrics to a JSON file."""
    logger = EnergyLogger()
    outfile = tmp_path / "metrics.json"
    logger.log_metrics("unit_test")
    logger.export_metrics(str(outfile))

    # Read file and check expected keys
    text = outfile.read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict)
    assert "summary" in data
    assert "metrics" in data


def test_import_fails_if_psutil_missing(monkeypatch):
    """Test that import fails gracefully when psutil is missing."""
    original_module = sys.modules.get("carbon_ops.energy_logger")
    monkeypatch.delitem(sys.modules, "carbon_ops.energy_logger", raising=False)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "psutil" or name.startswith("psutil."):
            raise ImportError("psutil not available")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    try:
        with pytest.raises(ImportError):
            importlib.import_module("carbon_ops.energy_logger")
    finally:
        if original_module is not None:
            sys.modules["carbon_ops.energy_logger"] = original_module
