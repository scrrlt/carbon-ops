"""Tests for signer helpers and JSON verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from carbon_ops.tools.verify import Signer, verify_json


def test_signer_signature_and_algorithm() -> None:
    signer = Signer(ephemeral=True)
    payload = {"message": "hello"}
    signed = signer.sign(payload)

    assert signed["signature_algorithm"] == "ed25519"
    assert "signature" in signed and "signing_key" in signed
    signature_int = int(signed["signature"], 16)
    assert signature_int >= 0

    ok, original = verify_json(signed, signed["signing_key"])
    assert ok
    assert original == payload


def test_verify_signer_plugins(tmp_path: Path) -> None:
    signer = Signer(ephemeral=True)
    payload = {"message": "test"}
    signed = signer.sign(payload)

    signed_path = tmp_path / "signed.json"
    signed_path.write_text(json.dumps(signed))

    loaded = json.loads(signed_path.read_text())
    signature_int = int(loaded["signature"], 16)
    assert signature_int >= 0

    ok, original = verify_json(loaded, loaded["signing_key"])
    if not ok:
        pytest.fail("verify_json rejected a signed payload produced by Signer")
    assert original == payload
