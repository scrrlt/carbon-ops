"""Tests for Unix domain socket helpers."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from carbon_ops.governor.ipc import (
    SocketSetup,
    bind_unix_socket_safe,
    cleanup_unix_socket,
)


@pytest.mark.skipif(
    os.name == "posix", reason="POSIX platforms covered via integration tests"
)
def test_bind_unix_socket_safe_on_non_posix(tmp_path: Path) -> None:
    """Binding on non-POSIX systems should raise OSError."""

    socket_path = tmp_path / "carbon-ops.sock"
    with pytest.raises(OSError):
        bind_unix_socket_safe(socket_path)


def test_cleanup_unix_socket_is_idempotent(tmp_path: Path) -> None:
    """Cleanup should tolerate missing files."""

    socket_path = tmp_path / "ghost.sock"
    sock = socket.socket()
    try:
        setup = SocketSetup(socket=sock, path=socket_path)
        cleanup_unix_socket(setup)
    finally:
        sock.close()
    assert not socket_path.exists()
