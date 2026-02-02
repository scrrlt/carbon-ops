"""Pytest configuration and fixtures."""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

try:  # pragma: no cover - runtime optional dependency
    import pytest_benchmark  # noqa: F401
except ImportError:  # pragma: no cover - simplified fallback when plugin absent
    if "pytest_benchmark" not in sys.modules:
        stub = ModuleType("pytest_benchmark")

        def _stub_getattr(name: str) -> Any:
            """Surface missing pytest_benchmark features during tests."""

            raise AttributeError(
                "pytest_benchmark is not installed; attribute "
                f"{name!r} is unavailable in the test environment."
            )

        stub.__getattr__ = _stub_getattr  # type: ignore[attr-defined]
        sys.modules["pytest_benchmark"] = stub

    @pytest.fixture
    def benchmark() -> Callable[..., Any]:
        """Fallback benchmark fixture returning the callable result without metrics."""

        def _run(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        return _run


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: mark test as requiring an event loop")


def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    """Execute async test functions without requiring pytest-asyncio."""

    if inspect.iscoroutinefunction(pyfuncitem.obj):
        call_kwargs = {
            name: pyfuncitem.funcargs[name]
            for name in pyfuncitem._fixtureinfo.argnames  # type: ignore[attr-defined]
        }

        event_loop = asyncio.new_event_loop()
        try:
            event_loop.run_until_complete(pyfuncitem.obj(**call_kwargs))
        finally:
            event_loop.close()
        return True
    return None


# Ensure src/ is on sys.path for tests so the new src layout is used during test runs
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
