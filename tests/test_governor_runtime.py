"""Tests for the carbon governor runtime coordination layer."""

from __future__ import annotations

import asyncio
from collections import deque

import pytest

from carbon_ops.governor.rapl import RaplTopology
from carbon_ops.governor.runtime import GovernorRuntime, PollResult


class StubTopology(RaplTopology):
    """In-memory topology used to validate runtime behaviour."""

    def __init__(self, deltas: deque[dict[str, int]]) -> None:
        super().__init__(domains={})
        self._deltas = deltas
        self.tick_calls = 0

    def tick(self) -> dict[str, int]:
        self.tick_calls += 1
        try:
            return self._deltas[0]
        finally:
            if len(self._deltas) > 1:
                self._deltas.popleft()

    def snapshot(self) -> dict[str, int]:
        return {"package-0:intel-rapl:0": 1_000 * self.tick_calls}


@pytest.mark.asyncio
async def test_runtime_captures_poll_results() -> None:
    """The runtime should update the latest poll result after ticking."""

    topology = StubTopology(deque([{"package-0:intel-rapl:0": 120}]))
    runtime = GovernorRuntime(topology, poll_interval=0.01)

    assert runtime.latest() is None

    await runtime.start()
    try:
        await asyncio.sleep(0.05)
    finally:
        await runtime.stop()

    result = runtime.latest()
    assert isinstance(result, PollResult)
    assert result.deltas_uj["package-0:intel-rapl:0"] == 120
    assert result.totals_uj["package-0:intel-rapl:0"] == 1_000 * topology.tick_calls


@pytest.mark.asyncio
async def test_runtime_handles_stop_without_start() -> None:
    """Stopping without starting should be a no-op."""

    topology = StubTopology(deque([{"package-0:intel-rapl:0": 10}]))
    runtime = GovernorRuntime(topology)

    await runtime.stop()
    assert runtime.latest() is None
