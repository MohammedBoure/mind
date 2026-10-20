"""Authentication, credential isolation, and token lifecycle management for mind."""

from __future__ import annotations

from mind.core.auth.backends import (
    CredentialBackend,
    MockCredentialBackend,
    WindowsCredentialBackend,
)
from mind.core.auth.lock import CrossProcessCredentialLock
from mind.core.auth.manager import TokenManager
from mind.core.auth.models import (
    AuthError,
    KeyringStorageError,
    LockTimeoutError,
    TokenClaims,
    TokenExpiredError,
    TokenStatus,
    TokenValidationError,
    ValidationResult,
)
from mind.core.auth.validator import AuthValidator

__all__ = [
    "AuthError",
    "AuthValidator",
    "CredentialBackend",
    "CrossProcessCredentialLock",
    "KeyringStorageError",
    "LockTimeoutError",
    "MockCredentialBackend",
    "TokenClaims",
    "TokenExpiredError",
    "TokenManager",
    "TokenStatus",
    "TokenValidationError",
    "ValidationResult",
    "WindowsCredentialBackend",
]
