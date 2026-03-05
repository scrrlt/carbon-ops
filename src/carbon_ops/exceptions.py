"""Business domain exceptions for Carbon Ops.

This module defines specific exception types to replace generic exception handling
and provide better error diagnostics for carbon tracking and environmental auditing.
"""

from typing import Any


class CarbonOpsException(Exception):
    """Base exception for all Carbon Ops domain errors."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class CryptoError(CarbonOpsException):
    """Base class for cryptographic operation errors."""
    pass


class SignatureVerificationError(CryptoError):
    """Raised when cryptographic signature verification fails."""
    pass


class CryptoInitializationError(CryptoError):
    """Raised when cryptographic components fail to initialize."""
    pass


class KeyGenerationError(CryptoError):
    """Raised when cryptographic key generation fails."""
    pass


class LedgerError(CarbonOpsException):
    """Base class for ledger operation errors."""
    pass


class LedgerLockError(LedgerError):
    """Raised when ledger file locking fails."""
    pass


class LedgerCorruptionError(LedgerError):
    """Raised when ledger data is corrupted or invalid."""
    pass


class LedgerIntegrityError(LedgerError):
    """Raised when ledger integrity checks fail."""
    pass


class FileSystemError(CarbonOpsException):
    """Raised when file system operations fail."""
    pass


class ConfigurationError(CarbonOpsException):
    """Raised when system configuration is invalid."""
    pass


class NetworkError(CarbonOpsException):
    """Raised when external service communication fails."""
    pass


class ValidationError(CarbonOpsException):
    """Raised when data validation fails."""
    pass


class TelemetryError(CarbonOpsException):
    """Raised when telemetry collection or processing fails."""
    pass


class CarbonDataError(CarbonOpsException):
    """Raised when carbon emission calculation or data processing fails."""
    pass