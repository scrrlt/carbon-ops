"""IPC helpers for the carbon governor daemon."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final, cast

__all__ = [
    "SocketAlreadyInUseError",
    "SocketPermissionError",
    "SocketSetup",
    "bind_unix_socket_safe",
    "cleanup_unix_socket",
    "secure_unix_socket",
]

DEFAULT_PROBE_TIMEOUT: Final[float] = 0.1
AF_UNIX: Final[int | None] = getattr(socket, "AF_UNIX", None)


class SocketAlreadyInUseError(RuntimeError):
    """Raised when a live process is already bound to the socket path."""


class SocketPermissionError(RuntimeError):
    """Raised when socket permissions cannot be applied."""


@dataclass(slots=True)
class SocketSetup:
    """Bundle describing the socket and its filesystem path."""

    socket: socket.socket
    path: Path


def bind_unix_socket_safe(
    path: Path,
    *,
    probe_timeout: float = DEFAULT_PROBE_TIMEOUT,
    backlog: int = 5,
) -> SocketSetup:
    """Bind a Unix domain socket after clearing stale endpoints.

    Args:
        path: Location of the Unix domain socket.
        probe_timeout: Timeout used when probing an existing socket path.
        backlog: Listen backlog applied to the resulting socket.

    Returns:
        A :class:`SocketSetup` containing the bound socket.

    Raises:
        SocketAlreadyInUseError: If an active listener is already bound.
        OSError: If the host does not support Unix domain sockets.
    """

    if AF_UNIX is None:
        raise OSError("Unix domain sockets are not supported on this platform")

    if path.exists():
        if _probe_socket(path, probe_timeout):
            raise SocketAlreadyInUseError(f"Socket already in use: {path}")
        path.unlink()

    path.parent.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(path))
        sock.listen(backlog)
    except Exception:  # pragma: no cover - system-level error
        sock.close()
        raise

    return SocketSetup(socket=sock, path=path)


def secure_unix_socket(
    setup: SocketSetup,
    *,
    mode: int = 0o660,
    owner_uid: int = 0,
    group_name: str | None = None,
) -> None:
    """Apply ownership and permission hardening to a Unix domain socket.

    Args:
        setup: Bundle containing the socket and its path.
        mode: Filesystem permissions (default ``0o660``).
        owner_uid: Numeric user identifier that should own the socket (default
            ``0`` for root).
        group_name: Optional group name that should be granted access.

    Raises:
        SocketPermissionError: If the ownership or permissions cannot be set.
    """

    if os.name != "posix":  # pragma: no cover - platform guard
        raise SocketPermissionError(
            "Unix socket permissions are only supported on POSIX"
        )

    path = setup.path
    try:
        os.chmod(path, mode)
    except PermissionError as exc:  # pragma: no cover - permission guard
        raise SocketPermissionError(f"Failed to chmod {path}: {exc}") from exc

    gid = None
    if group_name:
        try:
            import grp as grp_module
        except ImportError:  # pragma: no cover - platform guard
            raise SocketPermissionError("Group management requires POSIX support")
        else:
            try:
                grp_any = cast(Any, grp_module)
                gid = int(grp_any.getgrnam(group_name).gr_gid)
            except KeyError as exc:
                raise SocketPermissionError(f"Group not found: {group_name}") from exc

    try:
        chown_fn = cast(Callable[[str, int, int], None], getattr(os, "chown"))
        chown_fn(str(path), owner_uid, -1 if gid is None else gid)
    except PermissionError as exc:  # pragma: no cover - permission guard
        raise SocketPermissionError(f"Failed to chown {path}: {exc}") from exc


def _probe_socket(path: Path, probe_timeout: float) -> bool:
    """Return whether ``path`` refers to a live Unix socket.

    Args:
        path: Socket path to probe.
        probe_timeout: Timeout used for the connection attempt.

    Returns:
        ``True`` if a listener responds to the probe, otherwise ``False``.
    """

    if AF_UNIX is None:
        return False

    try:
        with socket.socket(AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(probe_timeout)
            probe.connect(str(path))
    except FileNotFoundError:
        return False
    except (ConnectionRefusedError, TimeoutError, socket.timeout):
        return False
    except OSError:
        # For example, permission errors should be treated as "in use" to avoid
        # deleting sockets owned by another process.
        return True
    return True


def cleanup_unix_socket(setup: SocketSetup) -> None:
    """Remove the Unix domain socket file if it exists.

    Args:
        setup: Bundle describing the socket endpoint to clean up.
    """

    try:
        setup.path.unlink()
    except FileNotFoundError:  # pragma: no cover - already removed
        return
