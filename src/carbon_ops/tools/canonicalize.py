"""Deterministic JSON canonicalization and hashing helpers."""

from __future__ import annotations

import json
import hashlib


def canonicalize(obj: object) -> str:
    """
    Return deterministic JSON serialization for obj.

    Uses sort_keys and compact separators to ensure stable output for hashing
    and signing.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_canonical(obj: object) -> str:
    """Return SHA-256 hex digest over the canonicalized JSON representation."""
    s = canonicalize(obj)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
