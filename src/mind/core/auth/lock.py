"""Cross-process mutex and file synchronization for safe credential manipulation."""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path
import sys

logger = logging.getLogger("mind.auth.lock")

kernel32 = getattr(ctypes.windll, "kernel32", None) if sys.platform == "win32" else None


class CrossProcessCredentialLock:
    """Inter-process mutex and file lock preventing concurrent credential overwrites."""

    def __init__(self, name: str = r"Global\AgyCredentialMutex", lock_dir: Path | None = None):
        self.name = name
        self.handle = None
        self._lock_file = None
        self.lock_dir = lock_dir or (Path.home() / ".gemini" / "tokens")

    def __enter__(self) -> CrossProcessCredentialLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def acquire(self, timeout_ms: int = 15000) -> bool:
        """Acquire named Win32 mutex and atomic file lock."""
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
            lock_path = self.lock_dir / ".credential.lock"
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
        """Release file lock and Win32 mutex."""
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
