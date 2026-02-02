"""Client helpers for interacting with the carbon governor daemon."""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

__all__ = ["GovernorClient", "GovernorSnapshot", "GovernorUnavailableError"]

_DEFAULT_SOCKET_PATH: Final[Path] = Path("/var/run/carbon-ops.sock")
AF_UNIX: Final[int | None] = getattr(socket, "AF_UNIX", None)


class GovernorUnavailableError(RuntimeError):
    """Raised when the governor daemon cannot be reached."""


@dataclass(slots=True)
class GovernorSnapshot:
    """Snapshot of the governor's monotonic energy counters."""

    timestamp: float
    counters_uj: dict[str, int]

    @property
    def total_energy_uj(self) -> int:
        """Return the sum of all domain counters in microjoules."""

        return sum(self.counters_uj.values())


class GovernorClient:
    """Lightweight Unix domain socket client for the carbon governor."""

    def __init__(
        self,
        socket_path: Path | None = None,
        *,
        timeout: float = 0.2,
    ) -> None:
        if os.name != "posix" or AF_UNIX is None:  # pragma: no cover - platform guard
            raise GovernorUnavailableError(
                "Unix domain sockets are only supported on POSIX platforms"
            )
        self.socket_path = socket_path or _DEFAULT_SOCKET_PATH
        self.timeout = timeout

    def snapshot(self) -> GovernorSnapshot:
        """Fetch the latest energy counters from the governor daemon."""

        try:
            with socket.socket(cast(int, AF_UNIX), socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(str(self.socket_path))
                # Minimal request to trigger a response.
                sock.sendall(b"{}\n")
                payload = self._recv_until_newline(sock)
        except (OSError, TimeoutError) as exc:  # pragma: no cover - system dependent
            raise GovernorUnavailableError(
                f"Failed to communicate with governor at {self.socket_path}: {exc}"
            ) from exc

        try:
            message = json.loads(payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise GovernorUnavailableError("Invalid governor response payload") from exc

        counters = message.get("counters_uj")
        if not isinstance(counters, dict):
            raise GovernorUnavailableError("Governor response missing counters_uj")

        parsed_counters: dict[str, int] = {}
        for key, value in counters.items():
            try:
                parsed_counters[key] = int(value)
            except (TypeError, ValueError) as exc:
                raise GovernorUnavailableError(
                    f"Governor counter for domain '{key}' is not an integer"
                ) from exc

        timestamp = float(message.get("timestamp", time.time()))
        return GovernorSnapshot(timestamp=timestamp, counters_uj=parsed_counters)

    @staticmethod
    def _recv_until_newline(sock: socket.socket) -> str:
        buffer = bytearray()
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            if b"\n" in chunk:
                break
        if not buffer:
            raise GovernorUnavailableError("Governor returned empty response")
        line = buffer.split(b"\n", 1)[0]
        return line.decode("utf-8", errors="replace")
