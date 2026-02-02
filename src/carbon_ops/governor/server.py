"""Async IPC server for the carbon governor daemon."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

from carbon_ops.governor.ipc import (
    SocketSetup,
    bind_unix_socket_safe,
    cleanup_unix_socket,
    secure_unix_socket,
)
from carbon_ops.governor.runtime import GovernorRuntime, PollResult


async def start_ipc_server(
    runtime: GovernorRuntime,
    *,
    socket_path: Path,
    group_name: str | None = None,
    mode: int = 0o660,
) -> tuple[asyncio.AbstractServer, SocketSetup]:
    """Start a Unix domain socket server exposing runtime snapshots.

    Args:
        runtime: Active governor runtime providing energy snapshots.
        socket_path: Filesystem path for the Unix domain socket.
        group_name: Optional group that should own the socket alongside the
            effective user.
        mode: Filesystem permissions applied after binding.

    Returns:
        Tuple containing the asyncio server and the socket metadata.

    Raises:
        SocketPermissionError: If permissions cannot be applied after binding.
        OSError: For binding or runtime errors.
    """
    original_umask: int | None = None
    setup: SocketSetup
    try:
        if hasattr(os, "umask"):
            original_umask = os.umask(0o077)
        setup = bind_unix_socket_safe(socket_path)
    finally:
        if original_umask is not None:
            os.umask(original_umask)

    async def _handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            payload = await _serialize_snapshot(runtime)
            writer.write(payload)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    start_unix_server_callable = cast(
        Callable[..., Awaitable[asyncio.AbstractServer]] | None,
        getattr(asyncio, "start_unix_server", None),
    )
    if start_unix_server_callable is None:
        cleanup_unix_socket(setup)
        raise OSError("Unix domain sockets are not supported on this platform")

    server = await start_unix_server_callable(_handle, sock=setup.socket)

    try:
        owner_uid = int(getattr(os, "geteuid", lambda: 0)())
        secure_unix_socket(setup, mode=mode, owner_uid=owner_uid, group_name=group_name)
    except Exception:
        server.close()
        await server.wait_closed()
        cleanup_unix_socket(setup)
        raise

    return server, setup


async def _serialize_snapshot(runtime: GovernorRuntime) -> bytes:
    """Serialize the latest poll snapshot as a JSON document.

    Args:
        runtime: Runtime providing the latest poll result.

    Returns:
        UTF-8 encoded JSON payload suitable for socket transmission.
    """

    result: PollResult | None = runtime.latest()
    body: dict[str, object]
    if result is None:
        body = {"status": "warming_up"}
    else:
        body = {
            "status": "ok",
            "timestamp": result.timestamp,
            "deltas_uj": dict(result.deltas_uj),
            "totals_uj": dict(result.totals_uj),
        }
    return json.dumps(body, separators=(",", ":")).encode("utf-8") + b"\n"


__all__ = ["start_ipc_server"]
