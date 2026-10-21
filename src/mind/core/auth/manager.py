"""Token lifecycle coordinator and slot credential isolation manager."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
import time

from mind.core.auth.backends import CredentialBackend, WindowsCredentialBackend
from mind.core.auth.lock import CrossProcessCredentialLock
from mind.core.auth.validator import AuthValidator

logger = logging.getLogger("mind.auth.manager")


class TokenManager:
    """Manages slot token persistence, keyring synchronization, and process environments."""

    def __init__(
        self,
        backend: CredentialBackend | None = None,
        validator: AuthValidator | None = None,
        tokens_dir: Path | None = None,
        instances_dir: Path | None = None,
        lock_name: str = r"Global\AgyCredentialMutex",
    ) -> None:
        self.backend: CredentialBackend = backend or WindowsCredentialBackend()
        self.validator: AuthValidator = validator or AuthValidator()
        self.tokens_dir: Path = tokens_dir or (Path.home() / ".gemini" / "tokens")
        self.instances_dir: Path = instances_dir or (Path.home() / ".gemini" / "instances")
        self.lock_name: str = lock_name

    def get_slot_path(self, slot: int) -> Path:
        """Return the path to the slot's token file."""
        return self.tokens_dir / f"agy{slot}.token"

    def get_instance_dir(self, slot: int) -> Path:
        """Return the path to the isolated instance directory for the slot."""
        return self.instances_dir / f"agy{slot}"

    def get_instance_token_path(self, slot: int) -> Path:
        """Return the path to the instance token file (token.json)."""
        return self.get_instance_dir(slot) / "token.json"

    def write_slot_token(self, slot: int, token_bytes: bytes) -> bool:
        """Write token bytes to slot storage atomically (syncing to both tokens and instances)."""
        sanitized = self.validator.sanitize(token_bytes)
        if not sanitized:
            return False

        slot_file = self.get_slot_path(slot)
        targets = [slot_file]

        inst_dir = self.get_instance_dir(slot)
        if inst_dir.exists():
            targets.append(self.get_instance_token_path(slot))

        success = True
        for target_path in targets:
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False) as tf:
                    tf.write(sanitized)
                    temp_path = Path(tf.name)
                temp_path.replace(target_path)
            except Exception as e:
                logger.error("Failed to write token file %s: %s", target_path, e)
                success = False
        return success

    def restore_slot(self, slot: int, target_name: str = "gemini:antigravity") -> bool:
        """Atomically read slot token, validate/sanitize it, and store into system backend under lock."""
        token_file = self.get_slot_path(slot)
        inst_token = self.get_instance_token_path(slot)

        target_file = None
        if token_file.exists():
            target_file = token_file
        elif inst_token.exists():
            target_file = inst_token

        if not target_file:
            logger.warning("Token file for slot agy%d does not exist at %s or %s", slot, token_file, inst_token)
            return False

        try:
            raw_bytes = target_file.read_bytes().strip()
            if not raw_bytes:
                return False

            had_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
            clean_bytes = self.validator.sanitize(raw_bytes)
            if not clean_bytes:
                return False

            if had_bom:
                try:
                    self.write_slot_token(slot, clean_bytes)
                except Exception:
                    pass

            with CrossProcessCredentialLock(name=self.lock_name, lock_dir=self.tokens_dir):
                success = self.backend.write(target_name, clean_bytes)
                time.sleep(0.05)
                return success
        except Exception as e:
            logger.error("Failed to restore credential for slot agy%d: %s", slot, e)
            return False

    def sync_slot_from_system(self, slot: int, target_name: str = "gemini:antigravity") -> bool:
        """Read system keyring token under lock and update slot token file if changed."""
        current_blob = self.backend.read(target_name)
        if not current_blob:
            return False

        clean_blob = self.validator.sanitize(current_blob)
        if not clean_blob:
            return False

        token_file = self.get_slot_path(slot)
        try:
            existing = (
                self.validator.sanitize(token_file.read_bytes())
                if token_file.exists()
                else b""
            )
            if clean_blob != existing:
                self.write_slot_token(slot, clean_blob)
                logger.info("Successfully updated token file for slot agy%d from keyring", slot)
                return True
        except Exception as e:
            logger.warning("Could not sync refreshed credential to agy%d: %s", slot, e)
        return False

    def build_slot_environment(
        self,
        slot: int,
        base_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Construct sanitized environment variables for worker slot with instance isolation."""
        env = dict(os.environ if base_env is None else base_env)
        env["AGY_SLOT"] = str(slot)

        token_file = self.get_slot_path(slot)
        env["AGY_TOKEN_FILE"] = str(token_file)

        # Seamless multi-instance support matching agys:
        inst_dir = self.get_instance_dir(slot)
        if inst_dir.exists():
            env["USERPROFILE"] = str(inst_dir)
            env["HOME"] = str(inst_dir)
            env["AGY_INSTANCE_DIR"] = str(inst_dir)

        # Clean any directory overrides that prevent agy from reading global config and credentials
        env.pop("ANTIGRAVITY_GEMINI_DIR", None)
        env.pop("ANTIGRAVITY_APP_DATA_DIR", None)
        return env
