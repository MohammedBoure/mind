"""Authentication, credential isolation, and token lifecycle management for mind."""

from __future__ import annotations

from mind.core.auth.backends import (
    CredentialBackend,
    LinuxFileVaultBackend,
    LinuxKeyringBackend,
    MockCredentialBackend,
    WindowsCredentialBackend,
    get_default_backend,
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
    VaultEncryptionError,
)
from mind.core.auth.validator import AuthValidator

__all__ = [
    "AuthError",
    "AuthValidator",
    "CredentialBackend",
    "CrossProcessCredentialLock",
    "KeyringStorageError",
    "LinuxFileVaultBackend",
    "LinuxKeyringBackend",
    "LockTimeoutError",
    "MockCredentialBackend",
    "TokenClaims",
    "TokenExpiredError",
    "TokenManager",
    "TokenStatus",
    "TokenValidationError",
    "ValidationResult",
    "VaultEncryptionError",
    "WindowsCredentialBackend",
    "get_default_backend",
]
