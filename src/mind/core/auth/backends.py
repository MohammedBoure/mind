"""Storage backends for credential read/write operations."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
from typing import Dict, Protocol


class CredentialBackend(Protocol):
    """Protocol interface for credential storage backends."""

    def read(self, target_name: str) -> bytes | None:
        """Read credential blob for target_name."""
        ...

    def write(self, target_name: str, secret: bytes, user_name: str = "antigravity") -> bool:
        """Write secret blob for target_name."""
        ...

    def delete(self, target_name: str) -> bool:
        """Delete secret blob for target_name."""
        ...

logger = logging.getLogger("mind.auth.backends")

advapi32 = getattr(ctypes.windll, "advapi32", None) if sys.platform == "win32" else None

if sys.platform == "win32":
    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.c_char_p),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]


class WindowsCredentialBackend:
    """Credential storage backed by Windows Credential Manager (Advapi32)."""

    def read(self, target_name: str) -> bytes | None:
        """Read credential blob from Windows Credential Manager."""
        if sys.platform != "win32" or not advapi32:
            return None
        pcred = ctypes.POINTER(CREDENTIAL)()
        res = advapi32.CredReadW(target_name, 1, 0, ctypes.byref(pcred))
        if not res:
            return None
        try:
            cred = pcred.contents
            if cred.CredentialBlobSize > 0 and cred.CredentialBlob:
                return ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return None
        finally:
            advapi32.CredFree(pcred)

    def write(self, target_name: str, secret: bytes, user_name: str = "antigravity") -> bool:
        """Write secret blob to Windows Credential Manager target."""
        if sys.platform != "win32" or not advapi32:
            return False
        clean_bytes = secret.strip()
        c = CREDENTIAL()
        c.Flags = 0
        c.Type = 1  # CRED_TYPE_GENERIC
        c.TargetName = target_name
        c.Comment = None
        c.CredentialBlobSize = len(clean_bytes)
        c.CredentialBlob = clean_bytes
        c.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
        c.AttributeCount = 0
        c.Attributes = None
        c.TargetAlias = None
        c.UserName = user_name
        return bool(advapi32.CredWriteW(ctypes.byref(c), 0))

    def delete(self, target_name: str) -> bool:
        """Delete secret blob from Windows Credential Manager target."""
        if sys.platform != "win32" or not advapi32:
            return False
        return bool(advapi32.CredDeleteW(target_name, 1, 0))


class MockCredentialBackend:
    """In-memory credential store for deterministic testing and non-Windows environments."""

    def __init__(self, initial_data: Dict[str, bytes] | None = None) -> None:
        self._store: Dict[str, bytes] = dict(initial_data or {})

    def read(self, target_name: str) -> bytes | None:
        """Read credential bytes from dictionary store."""
        return self._store.get(target_name)

    def write(self, target_name: str, secret: bytes, user_name: str = "antigravity") -> bool:
        """Store credential bytes in dictionary store."""
        self._store[target_name] = secret.strip()
        return True

    def delete(self, target_name: str) -> bool:
        """Remove credential from dictionary store."""
        if target_name in self._store:
            del self._store[target_name]
            return True
        return False
