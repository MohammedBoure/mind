"""Credential Management and Slot Isolation for Antigravity CLI (Backwards-Compatible Facade).

This module acts as a facade layer delegating to the modular `mind.core.auth` package,
preserving complete backwards compatibility with existing consumers and test suites.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mind.core.auth import (
    AuthValidator,
    CrossProcessCredentialLock,
    TokenManager,
    WindowsCredentialBackend,
)
from mind.core.auth.backends import advapi32, CREDENTIAL  # re-export for compatibility
from mind.core.auth.lock import kernel32  # re-export for compatibility

logger = logging.getLogger("mind.credentials")

# Default global singletons for procedural legacy API
_default_backend = WindowsCredentialBackend()
_default_validator = AuthValidator()
_default_manager = TokenManager(backend=_default_backend, validator=_default_validator)


def extract_email_from_token(raw_token: str | bytes) -> str | None:
    """Extract email address from token JSON or JWT payload (BOM safe)."""
    return _default_validator.extract_email(raw_token)


def read_credential(target_name: str = "gemini:antigravity") -> bytes | None:
    """Read credential blob from Windows Credential Manager."""
    return _default_backend.read(target_name)


def write_credential(
    token_bytes: bytes,
    target_name: str = "gemini:antigravity",
    user_name: str = "antigravity",
) -> bool:
    """Write token blob to Windows Credential Manager target."""
    return _default_backend.write(target_name, token_bytes, user_name)


def get_slot_token_path(slot: int) -> Path:
    """Get the path to the slot's token file."""
    return _default_manager.get_slot_path(slot)


def restore_slot_credential(slot: int) -> bool:
    """Restore a slot's saved token into Windows Credential Manager under a lock."""
    return _default_manager.restore_slot(slot)


def sync_slot_credential_from_system(slot: int) -> bool:
    """Sync refreshed token from Windows Credential Manager back to the slot token file."""
    return _default_manager.sync_slot_from_system(slot)


def setup_slot_env(slot: int, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build isolated environment variables for an agy slot."""
    return _default_manager.build_slot_environment(slot, base_env)


__all__ = [
    "CREDENTIAL",
    "CrossProcessCredentialLock",
    "advapi32",
    "extract_email_from_token",
    "get_slot_token_path",
    "kernel32",
    "read_credential",
    "restore_slot_credential",
    "setup_slot_env",
    "sync_slot_credential_from_system",
    "write_credential",
]
