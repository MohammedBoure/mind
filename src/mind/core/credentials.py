"""Credential Management and Slot Isolation for Antigravity CLI.

Provides cross-process mutex locking, Windows Credential Manager synchronization,
slot-isolated environment setups, and token persistence for multi-agent workflows.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import re
import sys
import time

logger = logging.getLogger("mind.credentials")

advapi32 = getattr(ctypes.windll, "advapi32", None) if sys.platform == "win32" else None
kernel32 = getattr(ctypes.windll, "kernel32", None) if sys.platform == "win32" else None

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


class CrossProcessCredentialLock:
    """Inter-process mutex and file lock preventing concurrent credential overwrites."""

    def __init__(self, name: str = r"Global\AgyCredentialMutex"):
        self.name = name
        self.handle = None
        self._lock_file = None

    def __enter__(self) -> CrossProcessCredentialLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def acquire(self, timeout_ms: int = 15000) -> bool:
        """Acquire named Win32 mutex and file lock."""
        if sys.platform == "win32" and kernel32:
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            if not self.handle:
                self.handle = kernel32.CreateMutexW(None, False, r"Local\AgyCredentialMutex")
            if self.handle:
                # WAIT_OBJECT_0 = 0x00000000, WAIT_ABANDONED = 0x00000080
                res = kernel32.WaitForSingleObject(self.handle, timeout_ms)
                if res not in (0x0, 0x80):
                    logger.warning("Mutex wait timed out after %d ms", timeout_ms)

        try:
            lock_path = Path.home() / ".gemini" / "tokens" / ".credential.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_file = open(lock_path, "a+b")
            if sys.platform == "win32":
                import msvcrt
                self._lock_file.seek(0)
                try:
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_LOCK, 1)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("File lock exception: %s", e)
        return True

    def release(self) -> None:
        """Release mutex and file lock."""
        if self._lock_file:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self._lock_file.seek(0)
                    try:
                        msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                self._lock_file.close()
            except Exception:
                pass
            self._lock_file = None

        if self.handle and kernel32:
            try:
                kernel32.ReleaseMutex(self.handle)
                kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None


def extract_email_from_token(raw_token: str | bytes) -> str | None:
    """Extract email address from token JSON or JWT payload (BOM safe)."""
    if not raw_token:
        return None
    try:
        if isinstance(raw_token, bytes):
            text = raw_token.decode("utf-8", errors="ignore").lstrip("\ufeff").strip()
        else:
            text = raw_token.lstrip("\ufeff").strip()
        if not text:
            return None
        data = json.loads(text)
        id_tok = data.get("id_token") or (
            data.get("token", {}).get("id_token")
            if isinstance(data.get("token"), dict)
            else None
        )
        if not id_tok or not isinstance(id_tok, str):
            return None
        parts = id_tok.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            rem = len(payload) % 4
            if rem:
                payload += "=" * (4 - rem)
            claims = json.loads(
                base64.urlsafe_b64decode(payload.encode("utf-8")).decode(
                    "utf-8", errors="ignore"
                )
            )
            return claims.get("email")
    except Exception:
        pass
    return None


def read_credential(target_name: str = "gemini:antigravity") -> bytes | None:
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


def write_credential(
    token_bytes: bytes,
    target_name: str = "gemini:antigravity",
    user_name: str = "antigravity",
) -> bool:
    """Write token blob to Windows Credential Manager target."""
    if sys.platform != "win32" or not advapi32:
        return False
    clean_bytes = token_bytes.strip()
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


def get_slot_token_path(slot: int) -> Path:
    """Get the path to the slot's token file."""
    return Path.home() / ".gemini" / "tokens" / f"agy{slot}.token"


def restore_slot_credential(slot: int) -> bool:
    """Restore a slot's saved token into Windows Credential Manager under a lock."""
    token_file = get_slot_token_path(slot)
    if not token_file.exists():
        logger.warning("Token file for slot agy%d does not exist at %s", slot, token_file)
        return False
    try:
        raw_bytes = token_file.read_bytes().strip()
        if not raw_bytes:
            return False
        # Strip UTF-8 BOM if present so Go's json.Unmarshal never fails
        had_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
        token_bytes = raw_bytes[3:].strip() if had_bom else raw_bytes
        if had_bom:
            try:
                token_file.write_bytes(token_bytes)
            except Exception:
                pass
        with CrossProcessCredentialLock():
            success = write_credential(token_bytes)
            # Brief settling window
            time.sleep(0.05)
            return success
    except Exception as e:
        logger.error("Failed to restore credential for slot agy%d: %s", slot, e)
        return False


def sync_slot_credential_from_system(slot: int) -> bool:
    """Sync refreshed token from Windows Credential Manager back to the slot token file."""
    if sys.platform != "win32":
        return False
    current_blob = read_credential()
    if not current_blob:
        return False
    clean_blob = current_blob.lstrip(b"\xef\xbb\xbf").strip()
    if not clean_blob:
        return False
    token_file = get_slot_token_path(slot)
    try:
        existing = (
            token_file.read_bytes().lstrip(b"\xef\xbb\xbf").strip()
            if token_file.exists()
            else b""
        )
        if clean_blob != existing:
            token_file.write_bytes(clean_blob)
            logger.info("Successfully updated token file for slot agy%d from keyring", slot)
            return True
    except Exception as e:
        logger.warning("Could not sync refreshed credential to agy%d: %s", slot, e)
    return False


def setup_slot_env(slot: int, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build isolated environment variables for an agy slot.
    
    Avoids overriding ANTIGRAVITY_GEMINI_DIR or ANTIGRAVITY_APP_DATA_DIR to maintain
    seamless global authentication and prevent 'not logged in' OAuth prompts.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["AGY_SLOT"] = str(slot)

    token_file = get_slot_token_path(slot)
    env["AGY_TOKEN_FILE"] = str(token_file)

    # Clean any directory overrides that prevent agy from reading global config and Windows credentials
    env.pop("ANTIGRAVITY_GEMINI_DIR", None)
    env.pop("ANTIGRAVITY_APP_DATA_DIR", None)
    return env
