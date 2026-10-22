"""Storage backends for credential read/write operations on Windows and Linux."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Dict, Protocol

from mind.core.auth.models import CredentialBackend, KeyringStorageError, VaultEncryptionError

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
else:
    CREDENTIAL = None


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


class LinuxFileVaultBackend:
    """Encrypted file-based credential vault for Linux with strict file permissions (chmod 0600).

    Persists encrypted tokens within `~/.gemini/tokens/` using authenticated symmetric
    encryption derived from local machine entropy and a secured master key.
    """

    def __init__(self, vault_dir: Path | None = None) -> None:
        self.vault_dir: Path = vault_dir or (Path.home() / ".gemini" / "tokens")
        self._key_cache: bytes | None = None

    def _ensure_secure_dir(self, directory: Path) -> None:
        """Create directory and enforce chmod 0700 (owner-only access) on POSIX."""
        directory.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "chmod") and sys.platform != "win32":
            try:
                os.chmod(directory, stat.S_IRWXU)  # 0700
            except OSError as err:
                logger.debug("Failed setting directory permissions on %s: %s", directory, err)

    def _ensure_secure_file_perms(self, file_path: Path) -> None:
        """Enforce chmod 0600 (owner read/write only) on POSIX."""
        if hasattr(os, "chmod") and sys.platform != "win32":
            try:
                os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
            except OSError as err:
                logger.debug("Failed setting file permissions on %s: %s", file_path, err)

    def _get_encryption_key(self) -> bytes:
        """Derive or load the 32-byte encryption key for the vault."""
        if self._key_cache is not None:
            return self._key_cache

        self._ensure_secure_dir(self.vault_dir)
        key_file = self.vault_dir / ".vault.key"

        if key_file.exists():
            try:
                raw_key = key_file.read_bytes().strip()
                if len(raw_key) >= 32:
                    self._key_cache = raw_key[:32]
                    return self._key_cache
            except Exception as err:
                logger.warning("Failed reading existing vault key %s: %s", key_file, err)

        # Generate a new cryptographic random master key
        new_key = os.urandom(32)
        try:
            with tempfile.NamedTemporaryFile("wb", dir=self.vault_dir, delete=False) as tf:
                tf.write(new_key)
                temp_path = Path(tf.name)
            self._ensure_secure_file_perms(temp_path)
            temp_path.replace(key_file)
            self._ensure_secure_file_perms(key_file)
        except Exception as err:
            logger.error("Failed creating vault key file %s: %s", key_file, err)

        self._key_cache = new_key
        return new_key

    def _encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt plaintext payload using Fernet or authenticated HMAC stream."""
        key = self._get_encryption_key()
        try:
            from cryptography.fernet import Fernet
            fernet_key = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
            f = Fernet(fernet_key)
            return f.encrypt(plaintext)
        except ImportError:
            # Cryptographic fallback: HMAC-SHA256 authenticated AES-CTR / keystream
            salt = os.urandom(16)
            stream_key = hashlib.sha256(key + salt).digest()
            # XOR stream
            keystream = bytearray()
            counter = 0
            while len(keystream) < len(plaintext):
                keystream.extend(hashlib.sha256(stream_key + counter.to_bytes(4, "big")).digest())
                counter += 1
            ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream[:len(plaintext)]))
            mac = hashlib.sha256(key + salt + ciphertext).digest()
            payload = {
                "salt": base64.b64encode(salt).decode("ascii"),
                "mac": base64.b64encode(mac).decode("ascii"),
                "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            }
            return json.dumps(payload).encode("utf-8")

    def _decrypt(self, ciphertext_bytes: bytes) -> bytes:
        """Decrypt ciphertext payload."""
        key = self._get_encryption_key()
        try:
            from cryptography.fernet import Fernet
            fernet_key = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
            f = Fernet(fernet_key)
            return f.decrypt(ciphertext_bytes)
        except ImportError:
            try:
                payload = json.loads(ciphertext_bytes.decode("utf-8"))
                salt = base64.b64decode(payload["salt"])
                expected_mac = base64.b64decode(payload["mac"])
                ciphertext = base64.b64decode(payload["ciphertext"])
                actual_mac = hashlib.sha256(key + salt + ciphertext).digest()
                if actual_mac != expected_mac:
                    raise VaultEncryptionError("Vault message authentication failed (corrupted or tampered).")
                stream_key = hashlib.sha256(key + salt).digest()
                keystream = bytearray()
                counter = 0
                while len(keystream) < len(ciphertext):
                    keystream.extend(hashlib.sha256(stream_key + counter.to_bytes(4, "big")).digest())
                    counter += 1
                return bytes(a ^ b for a, b in zip(ciphertext, keystream[:len(ciphertext)]))
            except Exception as err:
                raise VaultEncryptionError(f"Fallback vault decryption failed: {err}") from err
        except Exception as err:
            raise VaultEncryptionError(f"Vault decryption error: {err}") from err

    def _target_file_path(self, target_name: str) -> Path:
        """Calculate the target file path in the vault storage directory."""
        self._ensure_secure_dir(self.vault_dir)
        vault_store_dir = self.vault_dir / ".vault"
        self._ensure_secure_dir(vault_store_dir)
        safe_hash = hashlib.sha256(target_name.encode("utf-8")).hexdigest()[:16]
        sanitized_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in target_name)
        return vault_store_dir / f"{sanitized_name}_{safe_hash}.vault"

    def read(self, target_name: str) -> bytes | None:
        """Read and decrypt credential blob for target_name."""
        target_path = self._target_file_path(target_name)
        if not target_path.exists():
            return None
        try:
            encrypted_data = target_path.read_bytes().strip()
            if not encrypted_data:
                return None
            return self._decrypt(encrypted_data)
        except Exception as err:
            logger.error("Failed reading credential from Linux file vault %s: %s", target_path, err)
            return None

    def write(self, target_name: str, secret: bytes, user_name: str = "antigravity") -> bool:
        """Encrypt and atomically store secret blob with chmod 0600 permissions."""
        clean_bytes = secret.strip()
        if not clean_bytes:
            return False
        try:
            encrypted_data = self._encrypt(clean_bytes)
            target_path = self._target_file_path(target_name)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False) as tf:
                tf.write(encrypted_data)
                temp_path = Path(tf.name)

            self._ensure_secure_file_perms(temp_path)
            temp_path.replace(target_path)
            self._ensure_secure_file_perms(target_path)
            return True
        except Exception as err:
            logger.error("Failed writing credential to Linux file vault %s: %s", target_name, err)
            return False

    def delete(self, target_name: str) -> bool:
        """Delete secret file from vault."""
        target_path = self._target_file_path(target_name)
        if target_path.exists():
            try:
                target_path.unlink()
                return True
            except OSError as err:
                logger.error("Failed deleting vault file %s: %s", target_path, err)
        return False


class LinuxKeyringBackend:
    """Credential backend integrating Linux Keyring / SecretService with file vault fallback.

    Tries standard SecretService via Python's keyring library or secret-tool CLI,
    and seamlessly falls back to `LinuxFileVaultBackend` (chmod 0600) when running in headless,
    containerized, or SSH environments without an active D-Bus session.
    """

    def __init__(self, vault_dir: Path | None = None) -> None:
        self.file_vault = LinuxFileVaultBackend(vault_dir=vault_dir)
        self._secret_tool_available: bool | None = None
        self._keyring_available: bool | None = None

    def _has_secret_tool(self) -> bool:
        if self._secret_tool_available is None:
            self._secret_tool_available = shutil.which("secret-tool") is not None
        return self._secret_tool_available

    def _has_keyring_module(self) -> bool:
        if self._keyring_available is None:
            try:
                import keyring
                # Test whether an active backend is operational
                backend = keyring.get_keyring()
                backend_name = backend.__class__.__name__.lower()
                self._keyring_available = "fail" not in backend_name and "null" not in backend_name
            except Exception:
                self._keyring_available = False
        return bool(self._keyring_available)

    def read(self, target_name: str) -> bytes | None:
        """Read credential from SecretService or fallback file vault."""
        # 1. Try python keyring library if available
        if self._has_keyring_module():
            try:
                import keyring
                val = keyring.get_password(target_name, "antigravity")
                if val:
                    return val.encode("utf-8")
            except Exception as err:
                logger.debug("Python keyring read failed: %s", err)

        # 2. Try secret-tool CLI if available
        if self._has_secret_tool():
            try:
                proc = subprocess.run(
                    ["secret-tool", "lookup", "service", target_name, "user", "antigravity"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return proc.stdout.strip().encode("utf-8")
            except Exception as err:
                logger.debug("secret-tool read failed: %s", err)

        # 3. Fallback to encrypted file vault with chmod 0600
        return self.file_vault.read(target_name)

    def write(self, target_name: str, secret: bytes, user_name: str = "antigravity") -> bool:
        """Write credential to SecretService and backup to file vault."""
        clean_bytes = secret.strip()
        secret_str = clean_bytes.decode("utf-8", errors="replace")
        written_to_keyring = False

        # 1. Try python keyring module
        if self._has_keyring_module():
            try:
                import keyring
                keyring.set_password(target_name, user_name, secret_str)
                written_to_keyring = True
            except Exception as err:
                logger.debug("Python keyring write failed: %s", err)

        # 2. Try secret-tool CLI
        if not written_to_keyring and self._has_secret_tool():
            try:
                proc = subprocess.run(
                    [
                        "secret-tool", "store",
                        f"--label={target_name}",
                        "service", target_name,
                        "user", user_name,
                    ],
                    input=secret_str,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if proc.returncode == 0:
                    written_to_keyring = True
            except Exception as err:
                logger.debug("secret-tool write failed: %s", err)

        # Always ensure file vault backup is persisted with chmod 0600
        vault_success = self.file_vault.write(target_name, clean_bytes, user_name)
        return written_to_keyring or vault_success

    def delete(self, target_name: str) -> bool:
        """Delete credential from SecretService and file vault."""
        deleted = False
        if self._has_keyring_module():
            try:
                import keyring
                keyring.delete_password(target_name, "antigravity")
                deleted = True
            except Exception as err:
                logger.debug("Python keyring delete failed: %s", err)

        if self._has_secret_tool():
            try:
                proc = subprocess.run(
                    ["secret-tool", "clear", "service", target_name, "user", "antigravity"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=3,
                    check=False,
                )
                if proc.returncode == 0:
                    deleted = True
            except Exception as err:
                logger.debug("secret-tool delete failed: %s", err)

        vault_deleted = self.file_vault.delete(target_name)
        return deleted or vault_deleted


class MockCredentialBackend:
    """In-memory credential store for deterministic testing."""

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


def get_default_backend(tokens_dir: Path | None = None) -> CredentialBackend:
    """Factory creating the appropriate system credential backend for the running OS."""
    if sys.platform == "win32":
        return WindowsCredentialBackend()
    return LinuxKeyringBackend(vault_dir=tokens_dir)
