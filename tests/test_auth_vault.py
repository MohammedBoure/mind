"""Comprehensive unit tests for Cross-Platform Credential & Token Vault, Dual-Sync, and Locking."""

import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from mind.core.auth import (
    AuthValidator,
    CrossProcessCredentialLock,
    LinuxFileVaultBackend,
    LinuxKeyringBackend,
    LockTimeoutError,
    MockCredentialBackend,
    TokenClaims,
    TokenManager,
    TokenStatus,
    WindowsCredentialBackend,
    get_default_backend,
)


def _make_jwt(email: str = "agent@corp.com", exp_offset: int = 3600, account: str = "CorpAgent") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode("utf-8").rstrip("=")
    exp_ts = int((datetime.now(timezone.utc) + timedelta(seconds=exp_offset)).timestamp())
    claims = {
        "email": email,
        "sub": "agent_987",
        "account": account,
        "exp": exp_ts,
        "iat": exp_ts - 3600,
        "iss": "accounts.google.com",
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"{header}.{payload}.sig"


# ==============================================================================
# 1. LinuxFileVaultBackend Tests (chmod 0600 & Encryption)
# ==============================================================================

def test_linux_file_vault_encryption_roundtrip():
    """Verify secrets are encrypted at rest and decrypted identically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_dir = Path(tmpdir)
        vault = LinuxFileVaultBackend(vault_dir=vault_dir)

        secret = b'{"token": "super_secret_payload_123"}'
        target = "gemini:antigravity"

        # Write secret
        assert vault.write(target, secret)

        # Verify physical file on disk is encrypted (does not contain plaintext)
        vault_file = vault._target_file_path(target)
        assert vault_file.exists()
        raw_disk_data = vault_file.read_bytes()
        assert secret not in raw_disk_data

        # Read back secret
        decrypted = vault.read(target)
        assert decrypted == secret

        # Read non-existent target returns None
        assert vault.read("non_existent_target") is None

        # Delete target
        assert vault.delete(target) is True
        assert vault.read(target) is None
        assert vault.delete(target) is False


def test_linux_file_vault_chmod_enforcement():
    """Verify chmod 0600 on files and 0700 on directories is called on POSIX."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_dir = Path(tmpdir)
        vault = LinuxFileVaultBackend(vault_dir=vault_dir)

        with patch("sys.platform", "linux"):
            with patch("os.chmod") as mock_chmod:
                vault.write("test_target", b"secret_data")
                # Verify os.chmod was invoked with 0o600 or 0o700
                assert mock_chmod.called
                called_modes = [call.args[1] for call in mock_chmod.call_args_list]
                assert any(mode in (stat.S_IRUSR | stat.S_IWUSR, 0o600) for mode in called_modes)


def test_linux_file_vault_fallback_encryption():
    """Verify HMAC/keystream fallback encryption when cryptography module is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_dir = Path(tmpdir)
        vault = LinuxFileVaultBackend(vault_dir=vault_dir)

        with patch.dict("sys.modules", {"cryptography.fernet": None}):
            secret = b'{"token": "fallback_test_secret"}'
            assert vault.write("fallback_target", secret)

            decrypted = vault.read("fallback_target")
            assert decrypted == secret


# ==============================================================================
# 2. LinuxKeyringBackend Tests (SecretService & Fallback)
# ==============================================================================

def test_linux_keyring_backend_fallback_to_file_vault():
    """Verify LinuxKeyringBackend falls back to LinuxFileVaultBackend when no SecretService exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_dir = Path(tmpdir)
        backend = LinuxKeyringBackend(vault_dir=vault_dir)
        backend._keyring_available = False
        backend._secret_tool_available = False

        secret = b'{"id_token": "token_for_headless_linux"}'
        assert backend.write("gemini:antigravity", secret)
        assert backend.read("gemini:antigravity") == secret
        assert backend.delete("gemini:antigravity") is True
        assert backend.read("gemini:antigravity") is None


def test_linux_keyring_backend_secret_tool_integration():
    """Verify secret-tool CLI integration when tool is present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_dir = Path(tmpdir)
        backend = LinuxKeyringBackend(vault_dir=vault_dir)
        backend._keyring_available = False
        backend._secret_tool_available = True

        mock_res = MagicMock(returncode=0, stdout='{"secret": "from_secret_tool"}\n')
        with patch("subprocess.run", return_value=mock_res) as mock_run:
            read_val = backend.read("gemini:antigravity")
            assert read_val == b'{"secret": "from_secret_tool"}'
            assert mock_run.called
            cmd = mock_run.call_args[0][0]
            assert "secret-tool" in cmd
            assert "lookup" in cmd


def test_get_default_backend_factory():
    """Verify factory returns appropriate backend depending on OS."""
    with patch("sys.platform", "win32"):
        b_win = get_default_backend()
        assert isinstance(b_win, WindowsCredentialBackend)

    with patch("sys.platform", "linux"):
        b_linux = get_default_backend()
        assert isinstance(b_linux, LinuxKeyringBackend)


# ==============================================================================
# 3. CrossProcessCredentialLock Tests
# ==============================================================================

def test_cross_process_credential_lock_lifecycle():
    """Verify context manager acquires and releases lock file properly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_dir = Path(tmpdir)
        lock = CrossProcessCredentialLock(lock_dir=lock_dir, timeout_ms=1000)
        assert not lock.is_acquired

        with lock:
            assert lock.is_acquired
            assert (lock_dir / ".credential.lock").exists()

        assert not lock.is_acquired


def test_cross_process_credential_lock_timeout_handling():
    """Verify LockTimeoutError is raised when lock cannot be acquired within timeout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_dir = Path(tmpdir)
        lock1 = CrossProcessCredentialLock(lock_dir=lock_dir, timeout_ms=500, raise_on_timeout=True)
        lock2 = CrossProcessCredentialLock(lock_dir=lock_dir, timeout_ms=100, raise_on_timeout=True)

        with lock1:
            # Simulate non-reentrant lock failure on lock2
            with patch.object(lock2, "acquire", return_value=False):
                with pytest.raises(LockTimeoutError):
                    with lock2:
                        pass


def test_cross_process_credential_lock_linux_flock_simulation():
    """Verify POSIX fcntl.flock code path when running on Linux."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_dir = Path(tmpdir)
        lock = CrossProcessCredentialLock(lock_dir=lock_dir, timeout_ms=500)

        mock_fcntl = MagicMock()
        with patch.dict("sys.modules", {"fcntl": mock_fcntl}):
            with patch("sys.platform", "linux"):
                assert lock.acquire(timeout_ms=500)
                assert lock.is_acquired
                lock.release()
                assert not lock.is_acquired
                assert mock_fcntl.flock.called


# ==============================================================================
# 4. Smart Token Validation & Claim Extraction Tests
# ==============================================================================

def test_auth_validator_raw_jwt_support():
    """Verify AuthValidator parses raw JWT strings directly without JSON wrapping."""
    validator = AuthValidator()
    jwt_str = _make_jwt("direct_jwt@domain.com", account="DirectUser")

    claims = validator.extract_claims(jwt_str)
    assert claims is not None
    assert claims.email == "direct_jwt@domain.com"
    assert claims.account == "DirectUser"
    assert claims.token_type == "JWT"

    result = validator.validate(jwt_str)
    assert result.status == TokenStatus.VALID
    assert result.is_valid


def test_auth_validator_utf16_bom_sanitization():
    """Verify AuthValidator strips UTF-16 LE and BE BOMs properly."""
    validator = AuthValidator()
    raw_json = '{"email": "utf16@example.com"}'

    # UTF-16 LE with BOM
    utf16_le = b"\xff\xfe" + raw_json.encode("utf-16-le")
    sanitized_le = validator.sanitize(utf16_le)
    assert sanitized_le == raw_json.encode("utf-8")

    # UTF-16 BE with BOM
    utf16_be = b"\xfe\xff" + raw_json.encode("utf-16-be")
    sanitized_be = validator.sanitize(utf16_be)
    assert sanitized_be == raw_json.encode("utf-8")


def test_auth_validator_oauth2_dict_parsing():
    """Verify AuthValidator extracts claims from OAuth2 response dictionary."""
    validator = AuthValidator()
    oauth_payload = {
        "access_token": "ya29.mock_token_123",
        "email": "oauth2@google.com",
        "account": "GoogleDev",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    payload_bytes = json.dumps(oauth_payload).encode("utf-8")

    claims = validator.extract_claims(payload_bytes)
    assert claims is not None
    assert claims.email == "oauth2@google.com"
    assert claims.account == "GoogleDev"
    assert claims.expires_at is not None
    assert not validator.is_expired(payload_bytes)
    assert validator.time_until_expiry(payload_bytes) > 0


def test_auth_validator_iso8601_expiry_parsing():
    """Verify AuthValidator correctly parses ISO 8601 string expiry dates."""
    validator = AuthValidator(clock_skew_seconds=0)
    # Expired timestamp
    expired_payload = {
        "email": "iso_expired@test.com",
        "expiry": "2020-01-01T00:00:00Z",
    }
    res_expired = validator.validate(json.dumps(expired_payload))
    assert res_expired.status == TokenStatus.EXPIRED
    assert not res_expired.is_valid

    # Future timestamp
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future_payload = {
        "email": "iso_future@test.com",
        "expiry": future_time,
    }
    res_future = validator.validate(json.dumps(future_payload))
    assert res_future.status == TokenStatus.VALID
    assert res_future.is_valid


# ==============================================================================
# 5. Dual-Sync Architecture Tests (Tokens & Instances)
# ==============================================================================

def test_token_manager_dual_write():
    """Verify write_slot_token writes simultaneously to central and instance paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        tokens_dir = root / "tokens"
        instances_dir = root / "instances"
        manager = TokenManager(
            backend=MockCredentialBackend(),
            tokens_dir=tokens_dir,
            instances_dir=instances_dir,
        )

        token_data = b'{"token": "slot1_token_data"}'
        assert manager.write_slot_token(slot=1, token_bytes=token_data, sync_both=True)

        central_file = manager.get_slot_path(1)
        instance_file = manager.get_instance_token_path(1)

        assert central_file.exists()
        assert instance_file.exists()
        assert central_file.read_bytes() == token_data
        assert instance_file.read_bytes() == token_data


def test_token_manager_sync_dual_central_to_instance():
    """Verify sync_dual creates instance token from central token when instance is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        tokens_dir = root / "tokens"
        instances_dir = root / "instances"
        manager = TokenManager(
            backend=MockCredentialBackend(),
            tokens_dir=tokens_dir,
            instances_dir=instances_dir,
        )

        central_file = manager.get_slot_path(2)
        central_file.parent.mkdir(parents=True, exist_ok=True)
        central_file.write_bytes(b'{"token": "central_only"}')

        instance_file = manager.get_instance_token_path(2)
        assert not instance_file.exists()

        assert manager.sync_dual(slot=2) is True
        assert instance_file.exists()
        assert instance_file.read_bytes() == b'{"token": "central_only"}'


def test_token_manager_sync_dual_instance_to_central():
    """Verify sync_dual creates central token from instance token when central is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        tokens_dir = root / "tokens"
        instances_dir = root / "instances"
        manager = TokenManager(
            backend=MockCredentialBackend(),
            tokens_dir=tokens_dir,
            instances_dir=instances_dir,
        )

        instance_file = manager.get_instance_token_path(3)
        instance_file.parent.mkdir(parents=True, exist_ok=True)
        instance_file.write_bytes(b'{"token": "instance_only"}')

        central_file = manager.get_slot_path(3)
        assert not central_file.exists()

        assert manager.sync_dual(slot=3) is True
        assert central_file.exists()
        assert central_file.read_bytes() == b'{"token": "instance_only"}'


def test_token_manager_sync_dual_newer_instance_wins():
    """Verify sync_dual detects newer instance modification timestamp and updates central."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        tokens_dir = root / "tokens"
        instances_dir = root / "instances"
        manager = TokenManager(
            backend=MockCredentialBackend(),
            tokens_dir=tokens_dir,
            instances_dir=instances_dir,
        )

        central_file = manager.get_slot_path(4)
        instance_file = manager.get_instance_token_path(4)

        central_file.parent.mkdir(parents=True, exist_ok=True)
        instance_file.parent.mkdir(parents=True, exist_ok=True)

        central_file.write_bytes(b'{"token": "older_central"}')
        time.sleep(0.05)
        instance_file.write_bytes(b'{"token": "newer_instance"}')

        assert manager.sync_dual(slot=4) is True
        assert central_file.read_bytes() == b'{"token": "newer_instance"}'


def test_token_manager_sync_all_slots():
    """Verify sync_all_slots discovers and synchronizes all slots across directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        tokens_dir = root / "tokens"
        instances_dir = root / "instances"
        manager = TokenManager(
            backend=MockCredentialBackend(),
            tokens_dir=tokens_dir,
            instances_dir=instances_dir,
        )

        # Slot 1 in central only
        s1_file = manager.get_slot_path(1)
        s1_file.parent.mkdir(parents=True, exist_ok=True)
        s1_file.write_bytes(b'{"token": "s1"}')

        # Slot 2 in instance only
        s2_file = manager.get_instance_token_path(2)
        s2_file.parent.mkdir(parents=True, exist_ok=True)
        s2_file.write_bytes(b'{"token": "s2"}')

        results = manager.sync_all_slots()
        assert results.get(1) is True
        assert results.get(2) is True

        assert manager.get_instance_token_path(1).read_bytes() == b'{"token": "s1"}'
        assert manager.get_slot_path(2).read_bytes() == b'{"token": "s2"}'
