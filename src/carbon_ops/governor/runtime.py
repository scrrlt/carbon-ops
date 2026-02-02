"""Async runtime for the privileged carbon governor daemon."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Mapping

from carbon_ops.governor.rapl import (
    RaplReadError,
    RaplTopology,
    RaplTopologyConfig,
    create_rapl_topology,
)
from carbon_ops.governor.ipc import SocketSetup, cleanup_unix_socket
from carbon_ops.telemetry.logging_pipeline import (
    configure_structured_logging,
    shutdown_listeners,
)

LOGGER = logging.getLogger("carbon_ops.governor")


EnergySnapshot = Mapping[str, int]


@dataclass(slots=True, frozen=True)
class PollResult:
    """Container describing the outcome of a polling cycle."""

    timestamp: float
    deltas_uj: Mapping[str, int]
    totals_uj: Mapping[str, int]


@dataclass(slots=True)
class GovernorRuntime:
    """Coordinate polling and snapshotting for the governance daemon."""

    topology: RaplTopology
    poll_interval: float = 0.1
    logger: logging.Logger = field(default=LOGGER)
    _running: bool = field(init=False, default=False)
    _poll_task: asyncio.Task[None] | None = field(init=False, default=None)
    _latest: PollResult | None = field(init=False, default=None)
    _lock: Lock = field(init=False, default_factory=Lock)

    async def start(self) -> None:
        """Start the polling loop if it is not already running."""

        if self._running:
            return
        self._running = True
        loop = asyncio.get_running_loop()
        self._poll_task = loop.create_task(
            self._poll_loop(), name="carbon-governor-poll"
        )

    async def stop(self) -> None:
        """Request graceful shutdown of the polling loop."""

        self._running = False
        if self._poll_task is None:
            return
        self._poll_task.cancel()
        try:
            await self._poll_task
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            pass
        finally:
            self._poll_task = None

    def latest(self) -> PollResult | None:
        """Return the most recently captured poll result.

        Returns:
            Snapshot representing the last successful poll, or ``None`` when
            the runtime has not yet captured a reading.
        """

        with self._lock:
            return self._latest

    async def _poll_loop(self) -> None:
        """Internal coroutine that runs the poll cycle at ``poll_interval``."""

        loop = asyncio.get_running_loop()
        while self._running:
            start = loop.time()
            try:
                result = await asyncio.to_thread(self._poll_once)
            except RaplReadError:
                self.logger.error("RAPL polling failed", exc_info=True)
                result = None

            if result is not None:
                with self._lock:
                    self._latest = result

            elapsed = loop.time() - start
            sleep_time = max(self.poll_interval - elapsed, 0.0)
            await asyncio.sleep(sleep_time)

    def _poll_once(self) -> PollResult:
        """Perform a single synchronous poll of the topology.

        Returns:
            Dataclass describing the delta and totals captured in the cycle.
        """

        deltas = dict(self.topology.tick())
        totals = dict(self.topology.snapshot())
        timestamp = time.time()
        return PollResult(timestamp=timestamp, deltas_uj=deltas, totals_uj=totals)


async def run_governor(
    *,
    config: RaplTopologyConfig | None = None,
    poll_interval: float = 0.1,
    socket_path: Path | None = None,
    group_name: str | None = None,
    socket_mode: int = 0o660,
) -> None:
    """Entry point that wires logging and begins the poll loop.

    Args:
        config: Optional topology discovery configuration.
        poll_interval: Interval between hardware polls in seconds.
        socket_path: Optional Unix domain socket path for IPC exposure.
        group_name: Optional POSIX group name applied to the socket.
        socket_mode: Filesystem permissions used for the socket.

    Raises:
        RaplNotAvailableError: Propagated when no domains can be discovered.
        RaplReadError: Propagated when sysfs files contain malformed data.
    """

    listener = configure_structured_logging(LOGGER)
    try:
        topology = create_rapl_topology(config)
    except Exception:
        shutdown_listeners([listener])
        raise

    runtime = GovernorRuntime(topology=topology, poll_interval=poll_interval)
    await runtime.start()

    server: asyncio.AbstractServer | None = None
    socket_setup: SocketSetup | None = None

    if socket_path is not None:
        from carbon_ops.governor.server import start_ipc_server

        server, socket_setup = await start_ipc_server(
            runtime,
            socket_path=socket_path,
            group_name=group_name,
            mode=socket_mode,
        )

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:  # pragma: no cover - external cancellation
        pass
    finally:
        await runtime.stop()
        if server is not None:
            server.close()
            await server.wait_closed()
        if socket_setup is not None:
            cleanup_unix_socket(socket_setup)
        shutdown_listeners([listener])


__all__ = [
    "EnergySnapshot",
    "GovernorRuntime",
    "PollResult",
    "run_governor",
]
