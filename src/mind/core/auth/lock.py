"""Cross-process mutex and file synchronization for safe credential manipulation on Windows and Linux."""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import stat
import sys
import threading
import time
from typing import Optional

from mind.core.auth.models import LockTimeoutError

logger = logging.getLogger("mind.auth.lock")

kernel32 = getattr(ctypes.windll, "kernel32", None) if sys.platform == "win32" else None

# Thread-local state for safe intra-process lock re-entrancy
_local_state = threading.local()


class CrossProcessCredentialLock:
    """Inter-process mutex and file lock preventing concurrent credential overwrites across workers."""

    def __init__(
        self,
        name: str = r"Global\AgyCredentialMutex",
        lock_dir: Path | None = None,
        timeout_ms: int = 15000,
        raise_on_timeout: bool = False,
    ) -> None:
        self.name: str = name
        self.handle = None
        self._lock_file = None
        self.lock_dir: Path = lock_dir or (Path.home() / ".gemini" / "tokens")
        self.timeout_ms: int = timeout_ms
        self.raise_on_timeout: bool = raise_on_timeout
        self._acquired: bool = False
        self._is_nested: bool = False

    def __enter__(self) -> CrossProcessCredentialLock:
        success = self.acquire(self.timeout_ms)
        if not success and self.raise_on_timeout:
            raise LockTimeoutError(f"Timed out acquiring credential lock {self.name} after {self.timeout_ms}ms")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    @property
    def is_acquired(self) -> bool:
        """Return True if the lock is currently held by this instance."""
        return self._acquired

    def acquire(self, timeout_ms: int | None = None) -> bool:
        """Acquire named Win32 mutex and atomic file lock with cross-platform timeout support."""
        # Check thread-local re-entrancy
        current_depth = getattr(_local_state, "agy_lock_depth", 0)
        if current_depth > 0:
            _local_state.agy_lock_depth = current_depth + 1
            self._is_nested = True
            self._acquired = True
            return True

        effective_timeout_ms = self.timeout_ms if timeout_ms is None else timeout_ms
        deadline = time.monotonic() + (effective_timeout_ms / 1000.0)

        # 1. Windows Named Mutex synchronization
        if sys.platform == "win32" and kernel32:
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            if not self.handle:
                # In non-elevated Windows sessions, Global\ namespace may fail; fallback to Local\
                self.handle = kernel32.CreateMutexW(None, False, r"Local\AgyCredentialMutex")
            if self.handle:
                # WAIT_OBJECT_0 = 0x00000000, WAIT_ABANDONED = 0x00000080
                res = kernel32.WaitForSingleObject(self.handle, effective_timeout_ms)
                if res not in (0x0, 0x80):
                    logger.warning("Named mutex %s wait timed out after %d ms", self.name, effective_timeout_ms)
                    self.release()
                    return False

        # 2. File lock synchronization (.credential.lock)
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
            if hasattr(os, "chmod") and sys.platform != "win32":
                try:
                    os.chmod(self.lock_dir, stat.S_IRWXU)  # chmod 0700
                except OSError:
                    pass

            lock_path = self.lock_dir / ".credential.lock"

            if sys.platform == "win32":
                self._lock_file = open(lock_path, "a+b")
                import msvcrt
                try:
                    self._lock_file.seek(0)
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_LOCK, 1)
                except Exception as err:
                    logger.debug("Win32 file lock note: %s", err)
            else:
                # Linux / POSIX: use fcntl.flock with non-blocking checks and retry loop
                import fcntl
                flags = os.O_CREAT | os.O_RDWR
                fd = os.open(lock_path, flags, 0o600)
                try:
                    os.chmod(lock_path, stat.S_IRUSR | stat.S_IWUSR)  # chmod 0600
                except OSError:
                    pass
                self._lock_file = open(fd, "a+b", closefd=True)

                acquired_flock = False
                while time.monotonic() < deadline:
                    try:
                        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired_flock = True
                        break
                    except (BlockingIOError, IOError):
                        time.sleep(0.025)

                if not acquired_flock:
                    logger.warning("Linux flock on %s timed out after %d ms", lock_path, effective_timeout_ms)
                    self.release()
                    return False

        except Exception as e:
            logger.debug("File lock exception: %s", e)

        _local_state.agy_lock_depth = 1
        self._acquired = True
        return True

    def release(self) -> None:
        """Release file lock and Win32 named mutex."""
        current_depth = getattr(_local_state, "agy_lock_depth", 0)
        if current_depth > 1:
            _local_state.agy_lock_depth = current_depth - 1
            self._acquired = False
            return

        _local_state.agy_lock_depth = 0
        self._acquired = False

        if self._lock_file:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self._lock_file.seek(0)
                    try:
                        msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                else:
                    try:
                        import fcntl
                        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
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
