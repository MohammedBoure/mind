"""Stateless authentication token validator, BOM sanitization, and claim parser."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

from mind.core.auth.models import TokenClaims, TokenStatus, ValidationResult

logger = logging.getLogger("mind.auth.validator")

# Regex to detect raw JWT strings (3 dot-separated base64url components)
JWT_REGEX = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


class AuthValidator:
    """Validates, sanitizes, and decodes authentication tokens across multiple provider formats."""

    def __init__(self, clock_skew_seconds: int = 60) -> None:
        self.clock_skew_seconds = clock_skew_seconds

    def sanitize(self, raw_token: str | bytes) -> bytes:
        """Strip UTF-8 / UTF-16 BOM, surrounding whitespace, and normalize to UTF-8 bytes."""
        if not raw_token:
            return b""

        # Convert strings to bytes with BOM detection
        if isinstance(raw_token, str):
            clean_str = raw_token.lstrip("\ufeff").strip()
            return clean_str.encode("utf-8")

        # Handle raw byte sequences
        b = raw_token
        # UTF-8 BOM (\xEF\xBB\xBF)
        if b.startswith(b"\xef\xbb\xbf"):
            b = b[3:]
        # UTF-16 LE BOM (\xFF\xFE)
        elif b.startswith(b"\xff\xfe"):
            try:
                b = b[2:].decode("utf-16-le").encode("utf-8")
            except Exception:
                pass
        # UTF-16 BE BOM (\xFE\xFF)
        elif b.startswith(b"\xfe\xff"):
            try:
                b = b[2:].decode("utf-16-be").encode("utf-8")
            except Exception:
                pass

        return b.strip()

    def _decode_jwt_payload(self, jwt_str: str) -> dict[str, Any] | None:
        """Decode base64url JWT payload segment into a dictionary."""
        parts = jwt_str.strip().split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        rem = len(payload) % 4
        if rem:
            payload += "=" * (4 - rem)
        try:
            decoded_bytes = base64.urlsafe_b64decode(payload.encode("utf-8"))
            claims = json.loads(decoded_bytes.decode("utf-8", errors="replace"))
            return claims if isinstance(claims, dict) else None
        except Exception as err:
            logger.debug("Failed decoding JWT payload: %s", err)
            return None

    def extract_claims(self, raw_token: str | bytes) -> TokenClaims | None:
        """Parse token payload and extract identity claims without raising exceptions."""
        clean_bytes = self.sanitize(raw_token)
        if not clean_bytes:
            return None

        text = clean_bytes.decode("utf-8", errors="replace").strip()

        # 1. Check if the input is directly a raw JWT string
        if JWT_REGEX.match(text):
            jwt_claims = self._decode_jwt_payload(text)
            if jwt_claims:
                return self._build_claims(jwt_claims, token_type="JWT")

        # 2. Parse as JSON object
        try:
            data = json.loads(text)
        except Exception as err:
            logger.debug("Input is neither raw JWT nor valid JSON: %s", err)
            return None

        if not isinstance(data, dict):
            return None

        # Check for nested id_token (Antigravity structure: {"token": {"id_token": ...}} or {"id_token": ...})
        id_tok = data.get("id_token")
        if not id_tok and isinstance(data.get("token"), dict):
            id_tok = data["token"].get("id_token")
        if not id_tok and isinstance(data.get("tokens"), dict):
            id_tok = data["tokens"].get("id_token")

        if id_tok and isinstance(id_tok, str):
            jwt_claims = self._decode_jwt_payload(id_tok)
            if jwt_claims:
                # Merge any outer top-level metadata
                merged_claims = dict(jwt_claims)
                for key in ("account", "email", "user"):
                    if key in data and key not in merged_claims:
                        merged_claims[key] = data[key]
                return self._build_claims(merged_claims, token_type="OAuth2/OIDC")

        # 3. Direct JSON token / OAuth2 claims payload
        return self._build_claims_from_dict(data)

    def _build_claims(self, claims_data: dict[str, Any], token_type: str = "Bearer") -> TokenClaims:
        """Construct TokenClaims from a decoded claims dictionary."""
        exp_val = claims_data.get("exp")
        iat_val = claims_data.get("iat")

        expires_at = (
            datetime.fromtimestamp(exp_val, tz=timezone.utc)
            if isinstance(exp_val, (int, float))
            else None
        )
        issued_at = (
            datetime.fromtimestamp(iat_val, tz=timezone.utc)
            if isinstance(iat_val, (int, float))
            else None
        )

        email = claims_data.get("email")
        subject = claims_data.get("sub") or claims_data.get("user_id")
        account = (
            claims_data.get("account")
            or claims_data.get("name")
            or claims_data.get("preferred_username")
            or email
            or subject
        )

        return TokenClaims(
            email=email,
            subject=subject,
            account=account,
            expires_at=expires_at,
            issued_at=issued_at,
            issuer=claims_data.get("iss"),
            token_type=token_type,
            raw_claims=claims_data,
        )

    def _build_claims_from_dict(self, data: dict[str, Any]) -> TokenClaims | None:
        """Extract claims from standard OAuth2 JSON structures without id_token."""
        # Find email / user
        email = data.get("email")
        if not email and isinstance(data.get("user"), dict):
            email = data["user"].get("email")

        subject = data.get("sub") or data.get("user_id")
        account = data.get("account") or data.get("name") or email or subject

        # Check expiration formats (timestamp or ISO 8601 string)
        expires_at = None
        exp_val = data.get("expires_at") or data.get("exp")
        if isinstance(exp_val, (int, float)):
            expires_at = datetime.fromtimestamp(exp_val, tz=timezone.utc)
        elif isinstance(data.get("expiry"), str):
            try:
                # Parse ISO-8601 (e.g. 2026-10-21T21:00:00Z)
                expires_at = datetime.fromisoformat(data["expiry"].replace("Z", "+00:00"))
            except ValueError:
                pass
        elif isinstance(data.get("expires_in"), (int, float)):
            expires_at = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + data["expires_in"],
                tz=timezone.utc,
            )

        if email or subject or account or expires_at or "access_token" in data:
            return TokenClaims(
                email=email,
                subject=subject,
                account=account,
                expires_at=expires_at,
                issuer=data.get("iss"),
                token_type=data.get("token_type", "OAuth2"),
                raw_claims=data,
            )
        return None

    def extract_email(self, raw_token: str | bytes) -> str | None:
        """Convenience method returning the email claim if present."""
        claims = self.extract_claims(raw_token)
        return claims.email if claims else None

    def extract_account(self, raw_token: str | bytes) -> str | None:
        """Convenience method returning the account identifier or email."""
        claims = self.extract_claims(raw_token)
        return claims.account if claims else None

    def is_expired(self, raw_token: str | bytes) -> bool:
        """Return True if the token has an expiration timestamp and is expired."""
        claims = self.extract_claims(raw_token)
        if not claims or not claims.expires_at:
            return False
        now = datetime.now(timezone.utc)
        return (claims.expires_at.timestamp() + self.clock_skew_seconds) < now.timestamp()

    def time_until_expiry(self, raw_token: str | bytes) -> float | None:
        """Return remaining seconds until token expires, or None if no expiry is specified."""
        claims = self.extract_claims(raw_token)
        if not claims or not claims.expires_at:
            return None
        now = datetime.now(timezone.utc)
        return max(0.0, (claims.expires_at - now).total_seconds())

    def validate(self, raw_token: str | bytes) -> ValidationResult:
        """Perform comprehensive validation: checks structure, parses claims, and checks temporal validity."""
        clean_bytes = self.sanitize(raw_token)
        if not clean_bytes:
            return ValidationResult(
                status=TokenStatus.EMPTY,
                error_message="Token is empty or blank.",
            )

        text = clean_bytes.decode("utf-8", errors="replace").strip()

        # Check valid JSON or valid JWT
        is_jwt = bool(JWT_REGEX.match(text))
        is_json = False
        if not is_jwt:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    is_json = True
                else:
                    return ValidationResult(
                        status=TokenStatus.MALFORMED,
                        sanitized_bytes=clean_bytes,
                        error_message="Token JSON payload must be an object.",
                    )
            except Exception as err:
                return ValidationResult(
                    status=TokenStatus.MALFORMED,
                    sanitized_bytes=clean_bytes,
                    error_message=f"JSON decoding error: {err}",
                )

        claims = self.extract_claims(clean_bytes)
        if claims and claims.expires_at:
            now = datetime.now(timezone.utc)
            if (claims.expires_at.timestamp() + self.clock_skew_seconds) < now.timestamp():
                return ValidationResult(
                    status=TokenStatus.EXPIRED,
                    claims=claims,
                    sanitized_bytes=clean_bytes,
                    error_message=f"Token expired at {claims.expires_at.isoformat()}.",
                )

        return ValidationResult(
            status=TokenStatus.VALID,
            claims=claims,
            sanitized_bytes=clean_bytes,
        )
