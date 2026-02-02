"""
Append-only transparency ledger utilities (NDJSON) with canonicalization, signing, and hash-chained integrity.

Each line is a signed JSON object (Ed25519) produced from a canonicalized
payload augmented with an optional prev_hash field. prev_hash equals SHA-256
of the canonicalized previous payload (pre-signing). Chain verification
requires signature validity and prev_hash continuity.

Windows users should note that the fallback locking implementation relies on
``msvcrt.locking`` and therefore cannot lock byte ranges larger than
approximately 2 GB. When ledger files approach that size the code raises a
warning and advises rotating the log to avoid partial locks. POSIX platforms
using ``portalocker`` or ``fcntl`` are unaffected.
"""

from __future__ import annotations

from pathlib import Path
import io
import json
import logging
import os
import sys
import tempfile
from contextlib import contextmanager
from typing import IO, Iterator

from .canonicalize import hash_canonical
from .verify import Signer, verify_json

logger = logging.getLogger(__name__)

# Use 32-bit signed INT_MAX (2**31 - 1) as the lock range to approximate a
# "whole file" lock when calling msvcrt.locking on Windows. The legacy C
# runtime `_locking` API documents the `l` (length) parameter as a signed
# 32-bit value, so larger ranges may overflow on 32-bit runtimes; see:
# https://learn.microsoft.com/cpp/c-runtime-library/reference/locking
# This constant is only used on Windows when the msvcrt-based locking fallback
# path is taken; it is not applied on POSIX platforms using portalocker or fcntl.
_WIN_MAX_LOCK_SIZE: int = 2**31 - 1
"""Maximum byte range used when emulating a whole-file lock on Windows with
msvcrt.locking(). Files larger than this value (roughly 2GB) are only
partially locked on Windows, which is a known limitation and may cause race
conditions for concurrent writes to very large ledger files. POSIX locking
via portalocker or fcntl is not affected by this limit."""


@contextmanager
def _acquire_ledger_lock(ledger_path: Path) -> Iterator[IO[bytes]]:
    """Acquire a cross-platform file lock for ledger rewrites."""
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_fp:
        _lock_file(lock_fp)
        try:
            yield lock_fp
        finally:
            _unlock_file(lock_fp)


def _read_last_nonempty_line_by_file(f: IO[bytes]) -> str | None:
    """Read the last non-empty line efficiently using 4KB blocks."""
    f.seek(0, io.SEEK_END)
    file_size = f.tell()
    if file_size == 0:
        return None

    block_size = 4096
    offset = file_size
    buffer = b""

    while offset > 0:
        read_len = min(block_size, offset)
        offset -= read_len
        f.seek(offset)
        chunk = f.read(read_len)
        buffer = chunk + buffer

        # Split by newline and look for non-empty lines
        lines = buffer.split(b"\n")
        valid_lines = [line_bytes for line_bytes in lines if line_bytes.strip()]

        if valid_lines:
            # Found the last non-empty line
            return valid_lines[-1].decode("utf-8", errors="replace")

    return None


def _lock_file(fp: IO[bytes]) -> None:
    """Acquire exclusive lock using portalocker."""
    # Check file size for Windows locking limitations
    try:
        position = fp.tell()
        fp.flush()
        fp.seek(0, io.SEEK_END)
        current_size = fp.tell()
        fp.seek(position)
        if sys.platform == "win32" and current_size > _WIN_MAX_LOCK_SIZE:
            raise NotImplementedError(
                f"Ledger file size ({current_size} bytes) exceeds Windows locking limit "
                f"({_WIN_MAX_LOCK_SIZE} bytes), which may cause data corruption in concurrent writes. "
                "Rotate the ledger file by stopping writers, archiving the current file, creating a new "
                "empty ledger at the original path, and then resuming writes. See project documentation "
                "on ledger rotation for further guidance."
            )
    except (OSError, io.UnsupportedOperation, ValueError) as exc:
        logger.debug("Unable to determine ledger size before locking: %s", exc)

    try:
        import portalocker

        portalocker.lock(fp, portalocker.LOCK_EX)
    except ImportError:
        try:
            import fcntl

            fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        except AttributeError:
            try:
                import msvcrt

                # Lock the effective file range
                msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, _WIN_MAX_LOCK_SIZE)
            except OSError as e:
                raise RuntimeError(f"Failed to lock file: {e}")


def _unlock_file(fp: IO[bytes]) -> None:
    """Release file lock using available system primitives."""
    try:
        import portalocker
    except ImportError:
        portalocker = None  # type: ignore[assignment]
    if portalocker is not None:
        try:
            portalocker.unlock(fp)
            return
        except Exception as exc:
            logger.warning("Failed to unlock with portalocker: %s", exc)

    try:
        import fcntl
    except ImportError:
        fcntl = None  # type: ignore[assignment]
    if fcntl is not None:
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
            return
        except OSError as exc:
            logger.warning("Failed to unlock with fcntl: %s", exc)

    try:
        import msvcrt
    except ImportError:
        msvcrt = None  # type: ignore[assignment]
    if msvcrt is not None:
        try:
            msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, _WIN_MAX_LOCK_SIZE)
            return
        except OSError as exc:
            logger.warning("Failed to unlock with msvcrt: %s", exc)
            raise


def _prev_hash_from_line(line: bytes) -> str | None:
    """Return the previous-entry hash if the signed line verifies."""
    try:
        signed_last = json.loads(line.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    public_key_hex = signed_last.get("signing_key")
    ok, original = (
        verify_json(signed_last, public_key_hex) if public_key_hex else (False, None)
    )
    if not ok or original is None:
        return None
    return hash_canonical(original)


def _fsync_directory(path: Path) -> None:
    """Durably flush directory metadata when supported by the platform."""
    if os.name == "nt":  # pragma: no cover - Windows does not need dir fsync
        return
    flags = getattr(os, "O_DIRECTORY", None)
    if flags is None:  # pragma: no cover - platform without O_DIRECTORY
        return
    fd = os.open(str(path), flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append_signed_entry(
    ledger_path: Path,
    payload: dict[str, object],
    signer: Signer,
    include_prev_hash: bool = True,
) -> dict[str, object]:
    """
    Append a signed entry to an NDJSON ledger using advisory file locking to ensure consistency across concurrent processes.

    Behavior:
    - Acquire exclusive lock on ledger file.
    - Read last canonicalized entry and compute prev_hash if requested.
    - Sign payload (with prev_hash attached) and append.

    Returns the signed entry written.
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    payload_to_sign: dict[str, object] = dict(payload)

    with _acquire_ledger_lock(ledger_path):
        temp_path: Path | None = None
        signed_entry: dict[str, object]
        try:
            with tempfile.NamedTemporaryFile(
                "w+b", dir=str(ledger_path.parent), delete=False
            ) as tmp:
                temp_path = Path(tmp.name)
                last_line: bytes | None = None
                if ledger_path.exists():
                    with ledger_path.open("rb") as src:
                        for line in src:
                            tmp.write(line)
                            if line.strip():
                                last_line = line.strip()

                if include_prev_hash and last_line is not None:
                    prev = _prev_hash_from_line(last_line)
                    if prev:
                        payload_to_sign = dict(payload_to_sign)
                        payload_to_sign["prev_hash"] = prev

                signed_entry = signer.sign(payload_to_sign)
                tmp.write(json.dumps(signed_entry).encode("utf-8") + b"\n")
                tmp.flush()
                try:
                    os.fsync(tmp.fileno())
                except OSError as exc:
                    logger.warning(
                        "Failed to fsync ledger temp file",
                        extra={"error": str(exc)},
                    )
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

        if temp_path is None:
            raise RuntimeError("Temporary ledger file was not created")
        try:
            os.replace(temp_path, ledger_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

        try:
            _fsync_directory(ledger_path.parent)
        except OSError as exc:
            logger.warning(
                "Failed to fsync ledger directory",
                extra={"error": str(exc)},
            )

    return signed_entry


def validate_ledger(
    ledger_path: Path,
    public_key_hex: str,
) -> tuple[bool, int]:
    """
    Validate an NDJSON ledger.

    Returns ``(ok, first_bad_line_number)``. If ``ok`` is ``False`` and the ledger
    exists, ``first_bad_line_number`` is the 1-based line index where validation
    failed. A value of ``-1`` indicates that the ledger file does not exist.
    """
    if not Path(ledger_path).exists():
        return False, -1

    prev_hash: str | None = None
    with Path(ledger_path).open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                signed = json.loads(line)
            except json.JSONDecodeError:
                return False, idx

            ok, original = verify_json(signed, public_key_hex)
            if not ok or original is None:
                return False, idx

            # Chain check
            current_hash = hash_canonical(original)
            if prev_hash is not None:
                if original.get("prev_hash") != prev_hash:
                    return False, idx
            prev_hash = current_hash

    return True, -1
