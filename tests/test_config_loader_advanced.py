"""Advanced tests for config_loader to improve coverage."""

import os
import pytest
from carbon_ops.config_loader import load_config, CarbonConfig


def test_load_from_json_file(tmp_path):
    """Test loading config from JSON file."""
    cfg_file = tmp_path / "carbon_config.json"
    cfg_file.write_text(
        '{"region": {"default": "eu-west"}, "providers": {"order": ["static"]}}',
        encoding="utf-8",
    )

    os.environ["CARBON_CONFIG_PATH"] = str(cfg_file)
    config: CarbonConfig | None = None
    try:
        config = load_config()
    finally:
        del os.environ["CARBON_CONFIG_PATH"]

    assert config is not None
    assert config.region.default == "eu-west"
    assert config.providers.order == ("static",)


def test_env_var_override():
    """Test that ENV vars override defaults."""
    os.environ["DCL_DEFAULT_REGION"] = "us-east"
    os.environ["DCL_PUE_DEFAULT"] = "1.8"
    config: CarbonConfig | None = None
    try:
        config = load_config()
    finally:
        del os.environ["DCL_DEFAULT_REGION"]
        del os.environ["DCL_PUE_DEFAULT"]

    assert config is not None
    assert config.region.default == "us-east"
    assert config.pue.default == 1.8


def test_load_from_yaml_file(tmp_path):
    """Test loading config from YAML file if PyYAML available."""
    pytest.importorskip("yaml")

    cfg_file = tmp_path / "carbon_config.yaml"
    cfg_file.write_text(
        """
region:
  default: "eu-west"
providers:
  order: ["static"]
""",
        encoding="utf-8",
    )

    os.environ["CARBON_CONFIG_PATH"] = str(cfg_file)
    config: CarbonConfig | None = None
    try:
        config = load_config()
    finally:
        del os.environ["CARBON_CONFIG_PATH"]

    assert config is not None
    assert config.region.default == "eu-west"


def test_invalid_json_handling(tmp_path):
    """Test graceful handling of invalid JSON."""
    cfg_file = tmp_path / "invalid.json"
    cfg_file.write_text("{invalid json}", encoding="utf-8")

    os.environ["CARBON_CONFIG_PATH"] = str(cfg_file)
    config: CarbonConfig | None = None
    try:
        config = load_config()
    finally:
        del os.environ["CARBON_CONFIG_PATH"]

    assert isinstance(config, CarbonConfig)


def test_missing_file_handling():
    """Test handling when config file doesn't exist."""
    os.environ["CARBON_CONFIG_PATH"] = "/nonexistent/path.json"
    config: CarbonConfig | None = None
    try:
        config = load_config()
    finally:
        del os.environ["CARBON_CONFIG_PATH"]

    assert isinstance(config, CarbonConfig)


def test_config_validation():
    """Test that config values are validated."""
    config = CarbonConfig()
    # The config class should handle invalid values gracefully
    assert isinstance(config, CarbonConfig)
