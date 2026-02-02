"""Stress/validation tests for ledger chaining utilities."""

from pathlib import Path
from carbon_ops.tools.ledger import append_signed_entry, validate_ledger
from carbon_ops.tools.verify import Signer


def test_ledger_chain_and_validate(tmp_path: Path):
    """Test ledger chaining and validation."""
    ledger = tmp_path / "ledger.ndjson"
    # Simple, deterministic key for stress tests; do not reuse outside testing.
    signer = Signer(b"abcd" * 8)

    append_signed_entry(ledger, {"a": 1}, signer)
    append_signed_entry(ledger, {"b": 2}, signer)

    ok, _ = validate_ledger(ledger, signer.signing_key)
    assert ok
