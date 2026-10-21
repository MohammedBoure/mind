"""Authentication and credential data models, protocols, and exception hierarchy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class TokenStatus(str, Enum):
    """Enumeration of token validity states."""
    VALID = "valid"
    EXPIRED = "expired"
    MALFORMED = "malformed"
    EMPTY = "empty"


@dataclass(frozen=True)
class TokenClaims:
    """Decoded claims extracted from a token's identity payload."""
    email: str | None = None
    subject: str | None = None
    account: str | None = None
    expires_at: datetime | None = None
    issued_at: datetime | None = None
    issuer: str | None = None
    token_type: str | None = None
    raw_claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Return True if the token has expired past its temporal validity window."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def remaining_seconds(self) -> float:
        """Return remaining seconds until token expiration, or infinity if no expiry is set."""
        if self.expires_at is None:
            return float("inf")
        remaining = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of token validation and claim extraction."""
    status: TokenStatus
    claims: TokenClaims | None = None
    sanitized_bytes: bytes = b""
    error_message: str | None = None

    @property
    def is_valid(self) -> bool:
        """Return True if token status is valid."""
        return self.status == TokenStatus.VALID


@runtime_checkable
class CredentialBackend(Protocol):
    """Interface abstraction over secure OS keyring and vault storage."""

    def read(self, target_name: str) -> bytes | None:
        """Read a secret credential blob from storage."""
        ...

    def write(self, target_name: str, secret: bytes, user_name: str = "antigravity") -> bool:
        """Write a secret credential blob to storage."""
        ...

    def delete(self, target_name: str) -> bool:
        """Delete a secret credential from storage."""
        ...


class AuthError(Exception):
    """Base exception for all authentication and credential operations."""


class TokenValidationError(AuthError):
    """Raised when a token is malformed, corrupt, or missing expected structure."""


class TokenExpiredError(TokenValidationError):
    """Raised when a token has expired past its temporal validity window."""


class KeyringStorageError(AuthError):
    """Raised when underlying keyring or Windows Credential Manager operations fail."""


class LockTimeoutError(AuthError):
    """Raised when acquiring cross-process synchronization locks times out."""


class VaultEncryptionError(AuthError):
    """Raised when encrypting or decrypting credential vault files fails."""
