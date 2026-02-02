"""Tests for Ed25519 signing and verification."""

import importlib

import pytest

from carbon_ops.tools.verify import Signer


@pytest.mark.skipif(
    importlib.util.find_spec("cryptography") is None,
    reason="cryptography not installed",
)
def test_ed25519_sign_and_verify():
    """Test Ed25519 signing and verification."""
    # Only run when cryptography is available
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    # Deterministic (but non-trivial) key material for reproducible tests
    private_seed = bytes.fromhex(
        "9f2c4b7a1d08e3f5a6b0c3d4e7f812349abcedf00123456789abcdef01234567"
    )
    signer = Signer(private_seed)
    assert signer.algorithm == "ed25519"

    payload = {"hello": "world"}
    signed = signer.sign(payload)

    sig_hex = signed.get("signature")
    assert isinstance(sig_hex, str) and sig_hex

    pub_hex = signed.get("signing_key")
    assert isinstance(pub_hex, str) and pub_hex

    sig_bytes = bytes.fromhex(sig_hex)
    pub_bytes = bytes.fromhex(pub_hex)

    pub = Ed25519PublicKey.from_public_bytes(pub_bytes)
    # Reconstruct canonicalized bytes and verify
    from carbon_ops.tools.verify import canonicalize

    data = canonicalize(payload).encode("utf-8")
    pub.verify(sig_bytes, data)
