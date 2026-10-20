"""Unit tests for the refactored modular authentication system (mind.core.auth)."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile

import pytest

from mind.core.auth import (
    AuthValidator,
    MockCredentialBackend,
    TokenClaims,
    TokenExpiredError,
    TokenManager,
    TokenStatus,
    TokenValidationError,
    ValidationResult,
)
import mind.core.credentials as legacy_credentials


def _generate_jwt_payload(email: str = "test@example.com", exp_offset_seconds: int = 3600) -> str:
    import base64
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode("utf-8").rstrip("=")
    exp_ts = int((datetime.now(timezone.utc) + timedelta(seconds=exp_offset_seconds)).timestamp())
    iat_ts = exp_ts - 3600
    claims_dict = {
        "email": email,
        "sub": "user_12345",
        "exp": exp_ts,
        "iat": iat_ts,
        "iss": "accounts.google.com",
    }
    claims_bytes = json.dumps(claims_dict).encode("utf-8")
    payload = base64.urlsafe_b64encode(claims_bytes).decode("utf-8").rstrip("=")
    signature = "mock_sig"
    return f"{header}.{payload}.{signature}"


def test_validator_sanitize_bom_and_whitespace():
    """Verify UTF-8 BOM and whitespace stripping."""
    validator = AuthValidator()
    raw = b"\xef\xbb\xbf  {\"key\": \"value\"}  "
    clean = validator.sanitize(raw)
    assert clean == b'{"key": "value"}'

    clean_str = validator.sanitize("\ufeff  {\"key\": \"val\"} ")
    assert clean_str == b'{"key": "val"}'
    assert validator.sanitize(b"") == b""


def test_validator_extract_claims_and_email():
    """Verify claim extraction from nested and top-level JSON structures."""
    validator = AuthValidator()
    jwt = _generate_jwt_payload("user@test.org")
    token_json = json.dumps({"token": {"id_token": jwt}})

    claims = validator.extract_claims(token_json)
    assert claims is not None
    assert claims.email == "user@test.org"
    assert claims.subject == "user_12345"
    assert claims.issuer == "accounts.google.com"
    assert isinstance(claims.expires_at, datetime)
    assert validator.extract_email(token_json) == "user@test.org"


def test_validator_status_empty_and_malformed():
    """Verify validation statuses on empty and invalid tokens."""
    validator = AuthValidator()
    res_empty = validator.validate("")
    assert res_empty.status == TokenStatus.EMPTY
    assert not res_empty.is_valid

    res_malformed = validator.validate("not json")
    assert res_malformed.status == TokenStatus.MALFORMED
    assert not res_malformed.is_valid


def test_validator_expiration_detection():
    """Verify expiration checks with clock skew margin."""
    validator = AuthValidator(clock_skew_seconds=30)
    # Expired 2 hours ago
    expired_jwt = _generate_jwt_payload("expired@org.com", exp_offset_seconds=-7200)
    token_json = json.dumps({"id_token": expired_jwt})

    res = validator.validate(token_json)
    assert res.status == TokenStatus.EXPIRED
    assert not res.is_valid
    assert res.claims.email == "expired@org.com"

    # Valid token 1 hour into future
    valid_jwt = _generate_jwt_payload("valid@org.com", exp_offset_seconds=3600)
    valid_json = json.dumps({"id_token": valid_jwt})
    res_valid = validator.validate(valid_json)
    assert res_valid.status == TokenStatus.VALID
    assert res_valid.is_valid


def test_mock_credential_backend():
    """Test full lifecycle of MockCredentialBackend."""
    backend = MockCredentialBackend()
    assert backend.read("target1") is None

    assert backend.write("target1", b"secret_value")
    assert backend.read("target1") == b"secret_value"

    assert backend.delete("target1") is True
    assert backend.read("target1") is None
    assert backend.delete("target1") is False


def test_token_manager_slot_lifecycle():
    """Test slot token atomic write, restore, and system synchronization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tokens = Path(tmpdir)
        mock_backend = MockCredentialBackend()
        manager = TokenManager(backend=mock_backend, tokens_dir=tmp_tokens)

        # 1. Write token
        token_data = b'{"token": "xyz"}'
        assert manager.write_slot_token(slot=1, token_bytes=token_data)
        slot_file = manager.get_slot_path(1)
        assert slot_file.exists()
        assert slot_file.read_bytes() == token_data

        # 2. Restore slot into backend
        assert manager.restore_slot(slot=1, target_name="test_target")
        assert mock_backend.read("test_target") == token_data

        # 3. Simulate external refresh in system backend
        new_token_data = b'{"token": "refreshed_abc"}'
        mock_backend.write("test_target", new_token_data)
        assert manager.sync_slot_from_system(slot=1, target_name="test_target")
        assert slot_file.read_bytes() == new_token_data


def test_legacy_credentials_facade_compatibility():
    """Verify backwards-compatible facade functions."""
    jwt = _generate_jwt_payload("legacy@company.com")
    payload = json.dumps({"id_token": jwt})

    assert legacy_credentials.extract_email_from_token(payload) == "legacy@company.com"
    path = legacy_credentials.get_slot_token_path(2)
    assert path.name == "agy2.token"

    env = legacy_credentials.setup_slot_env(2, base_env={"TEST": "1"})
    assert env["AGY_SLOT"] == "2"
    assert "ANTIGRAVITY_GEMINI_DIR" not in env
