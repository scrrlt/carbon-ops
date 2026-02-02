"""
Tools package with small vendored helpers for signing and ledger operations.

These are intentionally minimal and dependency-free to avoid the chimera namespace
dependency leakage.
"""

from .ledger import append_signed_entry
from .verify import Signer, canonicalize

__all__ = ["append_signed_entry", "Signer", "canonicalize"]
