"""Token lifecycle coordinator and slot credential isolation manager."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from typing import Dict, List, Optional

from mind.core.auth.backends import CredentialBackend, get_default_backend
from mind.core.auth.lock import CrossProcessCredentialLock
from mind.core.auth.validator import AuthValidator

logger = logging.getLogger("mind.auth.manager")


class TokenManager:
    """Manages slot token persistence, keyring synchronization, dual-sync, and process environments."""

    def __init__(
        self,
        backend: CredentialBackend | None = None,
        validator: AuthValidator | None = None,
        tokens_dir: Path | None = None,
        instances_dir: Path | None = None,
        lock_name: str = r"Global\AgyCredentialMutex",
    ) -> None:
        self._custom_tokens_dir: bool = tokens_dir is not None
        self._custom_instances_dir: bool = instances_dir is not None
        self.tokens_dir: Path = tokens_dir or (Path.home() / ".gemini" / "tokens")
        self.instances_dir: Path = instances_dir or (Path.home() / ".gemini" / "instances")
        self.backend: CredentialBackend = backend or get_default_backend(self.tokens_dir)
        self.validator: AuthValidator = validator or AuthValidator()
        self.lock_name: str = lock_name

    def _ensure_dir_perms(self, directory: Path) -> None:
        """Create directory and enforce chmod 0700 permissions on POSIX systems."""
        directory.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "chmod") and sys.platform != "win32":
            try:
                os.chmod(directory, stat.S_IRWXU)  # 0700
            except OSError:
                pass

    def _ensure_file_perms(self, file_path: Path) -> None:
        """Enforce chmod 0600 (owner read/write only) on POSIX systems."""
        if hasattr(os, "chmod") and sys.platform != "win32":
            try:
                os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
            except OSError:
                pass

    def _atomic_write_file(self, target_path: Path, content: bytes) -> bool:
        """Atomically persist content to target_path with strict chmod 0600 permissions."""
        try:
            self._ensure_dir_perms(target_path.parent)
            with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False) as tf:
                tf.write(content)
                temp_path = Path(tf.name)

            self._ensure_file_perms(temp_path)
            temp_path.replace(target_path)
            self._ensure_file_perms(target_path)
            return True
        except Exception as err:
            logger.error("Failed atomic write to %s: %s", target_path, err)
            return False

    def get_slot_path(self, slot: int) -> Path:
        """Return the central path to the slot's token file (~/.gemini/tokens/agy<N>.token)."""
        return self.tokens_dir / f"agy{slot}.token"

    def get_instance_dir(self, slot: int) -> Path:
        """Return the path to the isolated instance directory (~/.gemini/instances/agy<N> or host agys)."""
        if self._custom_instances_dir:
            return self.instances_dir / f"agy{slot}"
        try:
            from mind.core.agent_discovery import get_slot_instance_dir
            return get_slot_instance_dir(slot)
        except Exception:
            return self.instances_dir / f"agy{slot}"

    def get_instance_token_path(self, slot: int) -> Path:
        """Return the path to the instance token file (~/.gemini/instances/agy<N>/token.json or host agys)."""
        if self._custom_instances_dir:
            return self.get_instance_dir(slot) / "token.json"
        try:
            from mind.core.agent_discovery import get_slot_instance_token_path
            return get_slot_instance_token_path(slot)
        except Exception:
            return self.get_instance_dir(slot) / "token.json"

    def write_slot_token(self, slot: int, token_bytes: bytes, sync_both: bool = True) -> bool:
        """Write token bytes to slot storage atomically (dual-syncing to central tokens and instance paths)."""
        sanitized = self.validator.sanitize(token_bytes)
        if not sanitized:
            return False

        central_path = self.get_slot_path(slot)
        targets = [central_path]

        if sync_both:
            targets.append(self.get_instance_token_path(slot))

        success = True
        for target_path in targets:
            if not self._atomic_write_file(target_path, sanitized):
                success = False
        return success

    def sync_dual(self, slot: int) -> bool:
        """Synchronize token bidirectionally between instance and central paths based on modification time."""
        central_path = self.get_slot_path(slot)
        instance_path = self.get_instance_token_path(slot)

        central_exists = central_path.exists()
        instance_exists = instance_path.exists()

        if not central_exists and not instance_exists:
            logger.debug("Dual-sync skipped for agy%d: neither central nor instance token exists", slot)
            return False

        # Case 1: Only central exists -> propagate to instance
        if central_exists and not instance_exists:
            try:
                content = self.validator.sanitize(central_path.read_bytes())
                if content:
                    return self._atomic_write_file(instance_path, content)
            except Exception as err:
                logger.warning("Dual-sync central->instance failed for agy%d: %s", slot, err)
                return False

        # Case 2: Only instance exists -> propagate to central
        if instance_exists and not central_exists:
            try:
                content = self.validator.sanitize(instance_path.read_bytes())
                if content:
                    return self._atomic_write_file(central_path, content)
            except Exception as err:
                logger.warning("Dual-sync instance->central failed for agy%d: %s", slot, err)
                return False

        # Case 3: Both exist -> compare modification timestamp and synchronize to newer
        try:
            central_mtime = central_path.stat().st_mtime
            inst_mtime = instance_path.stat().st_mtime

            central_bytes = self.validator.sanitize(central_path.read_bytes())
            inst_bytes = self.validator.sanitize(instance_path.read_bytes())

            if central_bytes == inst_bytes:
                return True

            if inst_mtime > central_mtime:
                # Instance was modified more recently
                logger.info("Dual-sync: instance token is newer for agy%d, updating central token", slot)
                return self._atomic_write_file(central_path, inst_bytes)
            else:
                # Central token is newer or equal
                logger.info("Dual-sync: central token is newer for agy%d, updating instance token", slot)
                return self._atomic_write_file(instance_path, central_bytes)
        except Exception as err:
            logger.error("Dual-sync comparison error for agy%d: %s", slot, err)
            return False

    def sync_all_slots(self) -> Dict[int, bool]:
        """Discover all configured slot numbers and execute dual-sync across all of them."""
        discovered_slots: set[int] = set()

        # Scan central tokens directory for agy<N>.token
        if self.tokens_dir.exists():
            for p in self.tokens_dir.glob("agy*.token"):
                match = re.match(r"^agy(\d+)\.token$", p.name)
                if match:
                    discovered_slots.add(int(match.group(1)))

        # Scan instances directory for agy<N>
        if self.instances_dir.exists():
            for p in self.instances_dir.iterdir():
                if p.is_dir():
                    match = re.match(r"^agy(\d+)$", p.name)
                    if match:
                        discovered_slots.add(int(match.group(1)))

        results: Dict[int, bool] = {}
        for slot in sorted(discovered_slots):
            results[slot] = self.sync_dual(slot)
        return results

    def restore_slot(self, slot: int, target_name: str = "gemini:antigravity") -> bool:
        """Atomically read slot token, run dual-sync, validate/sanitize, and write into system backend under lock."""
        # 1. Ensure dual-sync between central and instance before restoring
        self.sync_dual(slot)

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

            had_bom = raw_bytes.startswith(b"\xef\xbb\xbf") or raw_bytes.startswith(b"\xff\xfe")
            clean_bytes = self.validator.sanitize(raw_bytes)
            if not clean_bytes:
                return False

            # If token contained BOM, clean it on disk across both paths
            if had_bom:
                try:
                    self.write_slot_token(slot, clean_bytes, sync_both=True)
                except Exception:
                    pass

            # Acquire cross-process mutex and write to OS keyring / vault
            with CrossProcessCredentialLock(name=self.lock_name, lock_dir=self.tokens_dir):
                success = self.backend.write(target_name, clean_bytes)
                time.sleep(0.05)
                return success
        except Exception as e:
            logger.error("Failed to restore credential for slot agy%d: %s", slot, e)
            return False

    def sync_slot_from_system(self, slot: int, target_name: str = "gemini:antigravity") -> bool:
        """Read system keyring/vault token under lock and update both slot paths if changed."""
        with CrossProcessCredentialLock(name=self.lock_name, lock_dir=self.tokens_dir):
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
                self.write_slot_token(slot, clean_blob, sync_both=True)
                logger.info("Successfully updated token files for slot agy%d from keyring/vault", slot)
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
        from mind.core.agent_discovery import build_slot_isolation_env

        return build_slot_isolation_env(
            slot=slot,
            base_env=base_env,
            instances_root=self.instances_dir if self._custom_instances_dir else None,
            tokens_root=self.tokens_dir,
            auto_init=True,
        )
