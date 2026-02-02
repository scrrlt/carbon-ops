"""
Minimal signing and canonicalization helpers.

This module provides Ed25519 signing and deterministic canonicalization for
audit-grade logging. Ed25519 (cryptography package) is required. HMAC fallback
has been removed to preserve non-repudiation guarantees.

Provides:
- canonicalize(obj): deterministic JSON serialization
- Signer(private_key): Ed25519 signer class
- verify_json(signed, public_key_hex): verify Ed25519-signed JSON
"""

from __future__ import annotations

import json
import os

# Fields excluded from signature verification and signing envelope
SIGNATURE_FIELDS = ("signature", "signing_key", "signature_algorithm")


def canonicalize(obj: object) -> str:
    """
    Return a deterministic JSON serialization for `obj`.

    Uses sort_keys and separators that produce a compact deterministic
    representation suitable for hashing and signatures. Safely handles
    potentially hostile objects by restricting to basic JSON types.
    """

    class SafeJSONEncoder(json.JSONEncoder):
        """JSON encoder that only allows safe types to prevent hostile object attacks."""

        def default(self, o: object) -> object:
            # Only allow basic JSON types; reject custom objects that might
            # have malicious __repr__ or __str__ methods
            if isinstance(o, (str, int, float, bool, type(None))):
                return o
            elif isinstance(o, (list, tuple)):
                return list(o)  # Convert tuples to lists for consistency
            elif isinstance(o, dict):
                return dict(o)
            else:
                # Reject any other object types to prevent hostile serialization
                raise TypeError(
                    f"Object of type {type(o).__name__} is not JSON serializable"
                )

    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        cls=SafeJSONEncoder,
    )


def verify_json(
    signed: dict[str, object], public_key_hex: str | None
) -> tuple[bool, dict[str, object] | None]:
    """
    Verify a signed JSON object created by Signer.sign.

    Returns (ok, original_payload) where original_payload is the unsigned
    dict that was signed (i.e. signed minus signature/signing_key fields)
    when verification succeeds; otherwise (False, None).
    """
    if not isinstance(signed, dict):
        return False, None
    sig_hex = signed.get("signature")
    if not isinstance(sig_hex, str):
        return False, None
    # Reconstruct original payload (copy without signature metadata)
    original = {k: v for k, v in signed.items() if k not in SIGNATURE_FIELDS}
    data = canonicalize(original).encode("utf-8")

    # Ed25519 verification only
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception:
        # cryptography is required
        return False, None

    if not public_key_hex or not isinstance(public_key_hex, str):
        return False, None

    # Normalize hex (allow optional '0x' prefix)
    pk = public_key_hex
    if pk.startswith("0x") or pk.startswith("0X"):
        pk = pk[2:]
    # 64 hex chars = 32-byte Ed25519 public key
    if len(pk) != 64:
        return False, None

    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pk))
        pub.verify(bytes.fromhex(sig_hex), data)
        return True, original
    except Exception:
        return False, None


class Signer:
    """
    Signing abstraction using Ed25519.

    Args:
    ----
        private_key: Optional bytes. For Ed25519 it must be a 32-byte seed.
            When ``None``, a random 32-byte secret is generated if
            ``ephemeral=True``; otherwise a :class:`ValueError` is raised.
        ephemeral: If ``True``, allows generating an ephemeral key for testing.
            Defaults to ``False``.

    Attributes:
    ----------
        algorithm: Always ``"ed25519"``.
        signing_key: Hex identifier of the Ed25519 public key.

    """

    def __init__(
        self, private_key: bytes | None = None, ephemeral: bool = False
    ) -> None:
        """Initialize the Signer with a private key."""
        # Ed25519 is required for audit-grade signing. Fail fast if cryptography
        # is unavailable so administrators cannot accidentally run in symmetric
        # HMAC mode which weakens non-repudiation guarantees.
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )
            from cryptography.hazmat.primitives import serialization
        except Exception as exc:
            raise ImportError(
                "Ed25519 signing requires the 'cryptography' package (version 41.0.0 or newer). "
                "Install it with: pip install 'cryptography>=41.0.0'."
            ) from exc

        self._Ed25519PrivateKey = Ed25519PrivateKey
        self._serialization = serialization
        self.algorithm = "ed25519"

        if private_key is None:
            if not ephemeral:
                raise ValueError(
                    "private_key is required for audit-grade signing. "
                    "Provide a stable private key for production use, or set ephemeral=True for testing."
                )
            # Generate ephemeral key for testing
            private_key = os.urandom(32)
        if len(private_key) != 32:
            raise ValueError("private_key must be exactly 32 bytes for Ed25519")
        self._raw = bytes(private_key)

        self._priv = self._Ed25519PrivateKey.from_private_bytes(self._raw)
        pub = self._priv.public_key()
        pub_bytes = pub.public_bytes(
            encoding=self._serialization.Encoding.Raw,
            format=self._serialization.PublicFormat.Raw,
        )
        self.signing_key = pub_bytes.hex()

    def sign(self, payload: dict[str, object]) -> dict[str, object]:
        """
        Return a copy of payload augmented with signature metadata.

        The payload is canonicalized (deterministic JSON), then signed by the
        chosen algorithm. The returned dict contains `signature` (hex)
        and `signing_key`.
        """
        data = canonicalize(payload).encode("utf-8")

        out = dict(payload)
        sig = self._priv.sign(data)
        out["signature"] = sig.hex()
        out["signing_key"] = self.signing_key
        out["signature_algorithm"] = "ed25519"
        return out
