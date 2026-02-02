"""Tests enforcing dependency pinning policy for the distribution."""

from __future__ import annotations

from pathlib import Path

import tomllib


def test_all_dependencies_are_pinned() -> None:
    """Project dependencies must be pinned to exact versions."""

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    optional = data["project"].get("optional-dependencies", {})

    for requirement in dependencies:
        assert "==" in requirement, f"Core dependency not pinned: {requirement}"

    for group, requirements in optional.items():
        for requirement in requirements:
            assert "==" in requirement, (
                f"Optional dependency '{group}' not pinned: {requirement}"
            )
