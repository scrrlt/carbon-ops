"""Tests for tools and ledger functionality."""

import json
import hashlib
from pathlib import Path

from carbon_ops.schemas import AuditRecord, CURRENT_AUDIT_SCHEMA_VERSION
from carbon_ops.tools.ledger import append_signed_entry
from carbon_ops.tools.verify import Signer, canonicalize


def test_signer_and_canonicalize_roundtrip():
    """Test signer and canonicalize roundtrip."""
    payload = {"a": 1, "b": "x"}
    # Deterministic test key (32 bytes) for reproducible signatures
    signer = Signer(bytes(range(32)))
    signed = signer.sign(payload)
    assert "signature" in signed
    assert "signing_key" in signed
    # canonicalize produces deterministic JSON
    s1 = canonicalize(payload)
    s2 = canonicalize(payload)
    assert s1 == s2


def test_append_signed_entry_and_prev_hash(tmp_path: Path):
    """Test appending signed entries with prev_hash."""
    ledger = tmp_path / "ledger.ndjson"
    # Simple, predictable key for testing; acceptable only in non-production contexts.
    signer = Signer(b"abcd" * 8)

    first = {"x": 1}
    append_signed_entry(ledger, first, signer, include_prev_hash=False)
    assert ledger.exists()
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    # append second with prev hash
    second = {"y": 2}
    append_signed_entry(ledger, second, signer, include_prev_hash=True)
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    # Verify prev_hash on second matches hash of canonicalized payload of first line
    first_line = lines[0]
    first_entry = json.loads(first_line)
    # reconstruct original payload as signed by the first signer
    first_entry_payload = {
        k: v
        for k, v in first_entry.items()
        if k not in ("signature", "signing_key", "signature_algorithm")
    }
    expected = hashlib.sha256(
        canonicalize(first_entry_payload).encode("utf-8")
    ).hexdigest()

    # load second line JSON and confirm prev_hash equals expected
    second_entry = json.loads(lines[1])
    assert second_entry.get("prev_hash") == expected
    assert "signature" in second_entry
    assert "signing_key" in second_entry


def test_published_audit_schema_matches_model(tmp_path: Path) -> None:
    """Ensure the published JSON schema matches the Pydantic definition."""

    project_root = Path(__file__).resolve().parents[1]
    schema_path = project_root / f"audit_schema_v{CURRENT_AUDIT_SCHEMA_VERSION}.json"
    assert schema_path.exists(), "Audit schema artifact is missing"

    published = json.loads(schema_path.read_text(encoding="utf-8"))
    generated = AuditRecord.model_json_schema()

    # This ensures the committed JSON schema matches the runtime model; any
    # drift indicates the schema asset was not regenerated alongside code
    # changes.
    assert published == generated
