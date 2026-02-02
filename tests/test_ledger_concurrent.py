"""Tests for concurrent ledger operations."""

from __future__ import annotations

import json
import multiprocessing
import threading
from pathlib import Path

import pytest

from carbon_ops.tools.canonicalize import hash_canonical
from carbon_ops.tools.ledger import append_signed_entry, validate_ledger
from carbon_ops.tools.verify import Signer, verify_json


def append_ledger_entries_worker(
    ledger_path: str, seed_bytes: bytes, count: int
) -> None:
    """Worker function for concurrent appends."""

    from carbon_ops.tools.ledger import append_signed_entry
    from carbon_ops.tools.verify import Signer

    signer = Signer(seed_bytes)
    for index in range(count):
        append_signed_entry(
            Path(ledger_path), {"i": index}, signer, include_prev_hash=True
        )


# On platforms where "spawn" is already the default start method (for example,
# Windows and some CI runners), running this test under pytest can cause child
# processes to re-import the test module and fail to resolve the
# `append_ledger_entries_worker` target, sometimes leading to recursive imports
# or runaway process creation. Skip in that scenario and rely on the explicit
# "spawn" context used by the test below.
@pytest.mark.skipif(
    multiprocessing.get_start_method() == "spawn",
    reason="Skip when spawn is the global default to avoid recursive imports",
)
def test_concurrent_appends(tmp_path: Path) -> None:
    """Test concurrent appends to the ledger without polling."""

    ledger = tmp_path / "concurrent.ndjson"
    seed = bytes(range(32))
    proc_count = 4
    entries_per_process = 10

    # Use the explicit "spawn" context for parity across platforms; the test is
    # skipped above when spawn is already the global default to avoid recursive
    # process creation issues on certain runners.
    ctx = multiprocessing.get_context("spawn")
    processes: list[multiprocessing.Process] = []
    for _ in range(proc_count):
        process = ctx.Process(
            target=append_ledger_entries_worker,
            args=(str(ledger), seed, entries_per_process),
        )
        process.start()
        processes.append(process)

    for process in processes:
        process.join()
        assert (
            process.exitcode == 0
        ), f"Process {process.name} exited with {process.exitcode}"

    assert ledger.exists(), "Ledger file was not created"
    lines = [
        line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(lines) == proc_count * entries_per_process

    ok, bad = validate_ledger(ledger, Signer(seed).signing_key)
    assert ok, f"Ledger validation failed at line {bad}"

    entries = [json.loads(line) for line in lines]
    prev_hash = None
    for entry_index, entry in enumerate(entries):
        ok, canonical = verify_json(entry, Signer(seed).signing_key)
        assert ok, f"Entry {entry_index} verification failed"
        current_hash = hash_canonical(canonical)
        if entry_index == 0:
            assert "prev_hash" not in entry
        else:
            assert entry["prev_hash"] == prev_hash
        prev_hash = current_hash


def test_threading_concurrency(tmp_path: Path) -> None:
    """Test concurrent appends using threading (works on all platforms)."""

    ledger = tmp_path / "threading.ndjson"
    seed = bytes(range(32))
    num_threads = 4
    entries_per_thread = 5

    def append_worker(thread_id: int) -> None:
        signer = Signer(seed)
        for index in range(entries_per_thread):
            append_signed_entry(
                ledger,
                {"thread": thread_id, "i": index},
                signer,
                include_prev_hash=True,
            )

    threads = [
        threading.Thread(target=append_worker, args=(thread_id,))
        for thread_id in range(num_threads)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = [
        line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(lines) == num_threads * entries_per_thread

    ok, bad = validate_ledger(ledger, Signer(seed).signing_key)
    assert ok, f"Ledger validation failed at line {bad}"
