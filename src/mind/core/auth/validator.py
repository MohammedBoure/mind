"""Stateless authentication token validator, BOM sanitization, and JWT claim parser."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import logging
from typing import Any

from mind.core.auth.models import TokenClaims, TokenStatus, ValidationResult

logger = logging.getLogger("mind.auth.validator")


class AuthValidator:
    """Validates, cleans, and decodes authentication tokens."""

    def __init__(self, clock_skew_seconds: int = 60) -> None:
        self.clock_skew_seconds = clock_skew_seconds

    def sanitize(self, raw_token: str | bytes) -> bytes:
        """Strip UTF-8 BOM, whitespace, and normalize to UTF-8 bytes."""
        if not raw_token:
            return b""
        if isinstance(raw_token, str):
            clean_str = raw_token.lstrip("\ufeff").strip()
            return clean_str.encode("utf-8")
        # bytes
        if raw_token.startswith(b"\xef\xbb\xbf"):
            raw_token = raw_token[3:]
        return raw_token.strip()

    def extract_claims(self, raw_token: str | bytes) -> TokenClaims | None:
        """Parse token payload and extract identity claims without throwing."""
        clean_bytes = self.sanitize(raw_token)
        if not clean_bytes:
            return None

        try:
            text = clean_bytes.decode("utf-8", errors="ignore")
            data = json.loads(text)
            if not isinstance(data, dict):
                return None

            # Support both top-level and nested structure
            id_tok = data.get("id_token")
            if not id_tok and isinstance(data.get("token"), dict):
                id_tok = data.get("token", {}).get("id_token")

            if not id_tok or not isinstance(id_tok, str):
                return None

            parts = id_tok.split(".")
            if len(parts) < 2:
                return None

            payload = parts[1]
            rem = len(payload) % 4
            if rem:
                payload += "=" * (4 - rem)

            claims_data = json.loads(
                base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8", errors="ignore")
            )
            if not isinstance(claims_data, dict):
                return None

            exp_val = claims_data.get("exp")
            iat_val = claims_data.get("iat")
            expires_at = datetime.fromtimestamp(exp_val, tz=timezone.utc) if isinstance(exp_val, (int, float)) else None
            issued_at = datetime.fromtimestamp(iat_val, tz=timezone.utc) if isinstance(iat_val, (int, float)) else None

            return TokenClaims(
                email=claims_data.get("email"),
                subject=claims_data.get("sub"),
                expires_at=expires_at,
                issued_at=issued_at,
                issuer=claims_data.get("iss"),
                raw_claims=claims_data,
            )
        except Exception as e:
            logger.debug("Failed to extract claims: %s", e)
            return None

    def extract_email(self, raw_token: str | bytes) -> str | None:
        """Convenience method returning the email claim if present."""
        claims = self.extract_claims(raw_token)
        return claims.email if claims else None

    def validate(self, raw_token: str | bytes) -> ValidationResult:
        """Full validation checking structure, parsing JWT claims, and testing expiry."""
        clean_bytes = self.sanitize(raw_token)
        if not clean_bytes:
            return ValidationResult(
                status=TokenStatus.EMPTY,
                error_message="Token is empty or blank.",
            )

        try:
            text = clean_bytes.decode("utf-8", errors="ignore")
            data = json.loads(text)
            if not isinstance(data, dict):
                return ValidationResult(
                    status=TokenStatus.MALFORMED,
                    sanitized_bytes=clean_bytes,
                    error_message="Token JSON payload must be an object.",
                )
        except Exception as e:
            return ValidationResult(
                status=TokenStatus.MALFORMED,
                sanitized_bytes=clean_bytes,
                error_message=f"JSON decoding error: {e}",
            )

        claims = self.extract_claims(clean_bytes)
        if claims and claims.expires_at:
            now = datetime.now(timezone.utc)
            # Add clock skew margin
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
