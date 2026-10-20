"""Cross-platform Pseudoterminal (PTY) process abstraction.

Supports:
- Windows: pywinpty (ConPTY / winpty) with fallback to subprocess pipes.
- Unix: native pty/termios with master/slave pairs.
- Graceful termination and signal handling (Ctrl+C, SIGINT, SIGTERM) to prevent zombies.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Callable, Sequence

import psutil


class BasePtyProcess:
    """Abstract base interface for a spawned PTY process."""

    def __init__(self, on_output: Callable[[str], None] | None = None) -> None:
        self.on_output = on_output
        self._is_alive = True
        self._pid: int | None = None

    @property
    def pid(self) -> int | None:
        return self._pid

    def is_alive(self) -> bool:
        return self._is_alive

    def write(self, data: str) -> None:
        raise NotImplementedError

    def resize(self, columns: int, lines: int) -> None:
        raise NotImplementedError

    def send_interrupt(self) -> None:
        raise NotImplementedError

    def terminate(self, timeout: float = 2.0) -> None:
        raise NotImplementedError


# ── Windows winpty Implementation ──────────────────────────────────

class WindowsPtyProcess(BasePtyProcess):
    """Windows PTY process implemented using pywinpty."""

    def __init__(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        columns: int = 80,
        lines: int = 24,
        on_output: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(on_output=on_output)
        import winpty

        self._pty = winpty.PTY(columns, lines)

        # Parse command line
        if isinstance(command, (list, tuple)):
            appname = command[0]
            cmdline = subprocess.list2cmdline(command[1:]) if len(command) > 1 else ""
        else:
            parts = command.strip().split(maxsplit=1)
            appname = parts[0]
            cmdline = parts[1] if len(parts) > 1 else ""

        resolved_app = shutil.which(appname) or appname
        self._pty.spawn(resolved_app, cmdline=cmdline or None, cwd=cwd, env=env)
        self._pid = self._pty.pid
        self._stopped = False

        # Dedicated reader thread
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        while not self._stopped and self._pty.isalive():
            try:
                data = self._pty.read(blocking=True)
                if data:
                    if self.on_output:
                        self.on_output(data)
                else:
                    time.sleep(0.01)
            except Exception:
                break
        self._is_alive = False

    def write(self, data: str) -> None:
        if self._pty.isalive():
            self._pty.write(data)

    def resize(self, columns: int, lines: int) -> None:
        try:
            self._pty.set_size(max(20, columns), max(5, lines))
        except Exception:
            pass

    def send_interrupt(self) -> None:
        """Send Ctrl+C (\x03) directly to the console input buffer."""
        try:
            self.write("\x03")
        except Exception:
            pass

    def terminate(self, timeout: float = 2.0) -> None:
        self._stopped = True
        try:
            self._pty.cancel_io()
        except Exception:
            pass

        if self._pid:
            try:
                proc = psutil.Process(self._pid)
                # Terminate children first, then parent
                children = proc.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except Exception:
                        pass
                proc.terminate()
                _, alive = psutil.wait_procs(children + [proc], timeout=timeout)
                for p in alive:
                    try:
                        p.kill()
                    except Exception:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self._is_alive = False


# ── Unix PTY Implementation ────────────────────────────────────────

class UnixPtyProcess(BasePtyProcess):
    """Unix PTY process using termios/pty."""

    def __init__(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        columns: int = 80,
        lines: int = 24,
        on_output: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(on_output=on_output)
        import fcntl
        import pty
        import struct
        import termios

        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd
        self._slave_fd = slave_fd

        # Set initial terminal size
        winsize = struct.pack("HHHH", lines, columns, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        args = command if isinstance(command, list) else command.split()
        self._proc = subprocess.Popen(
            args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=env,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            close_fds=True,
        )
        os.close(slave_fd)
        self._pid = self._proc.pid
        self._stopped = False

        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        while not self._stopped and self._proc.poll() is None:
            try:
                data = os.read(self._master_fd, 4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                if self.on_output:
                    self.on_output(text)
            except OSError:
                break
        self._is_alive = False

    def write(self, data: str) -> None:
        try:
            os.write(self._master_fd, data.encode("utf-8"))
        except OSError:
            pass

    def resize(self, columns: int, lines: int) -> None:
        import fcntl
        import struct
        import termios

        try:
            winsize = struct.pack("HHHH", lines, columns, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def send_interrupt(self) -> None:
        try:
            self.write("\x03")
            if self._pid:
                os.kill(self._pid, signal.SIGINT)
        except OSError:
            pass

    def terminate(self, timeout: float = 2.0) -> None:
        self._stopped = True
        try:
            os.close(self._master_fd)
        except OSError:
            pass

        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self._proc.kill()
                except OSError:
                    pass
        self._is_alive = False


# ── Generic Pipe Fallback Implementation ───────────────────────────

class PipeFallbackProcess(BasePtyProcess):
    """Pipe-based fallback for environments where PTY creation fails."""

    def __init__(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(on_output=on_output)
        args = command if isinstance(command, list) else command.split()
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            bufsize=0,
        )
        self._pid = self._proc.pid
        self._stopped = False

        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        assert self._proc.stdout is not None
        while not self._stopped and self._proc.poll() is None:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                if self.on_output:
                    self.on_output(text)
            except Exception:
                break
        self._is_alive = False

    def write(self, data: str) -> None:
        if self._proc.stdin and not self._proc.stdin.closed:
            try:
                self._proc.stdin.write(data.encode("utf-8"))
                self._proc.stdin.flush()
            except Exception:
                pass

    def resize(self, columns: int, lines: int) -> None:
        pass  # Pipes do not support dynamic window sizing

    def send_interrupt(self) -> None:
        self.write("\x03")
        if self._pid:
            try:
                if sys.platform == "win32":
                    self._proc.send_signal(signal.CTRL_C_EVENT)
                else:
                    self._proc.send_signal(signal.SIGINT)
            except Exception:
                pass

    def terminate(self, timeout: float = 2.0) -> None:
        self._stopped = True
        try:
            self._proc.terminate()
            self._proc.wait(timeout=timeout)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._is_alive = False


# ── Spawner Factory Function ───────────────────────────────────────

def spawn_pty(
    command: str | list[str],
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    columns: int = 80,
    lines: int = 24,
    on_output: Callable[[str], None] | None = None,
) -> BasePtyProcess:
    """Spawn a cross-platform pseudo-terminal process with appropriate fallbacks."""
    if sys.platform == "win32":
        try:
            return WindowsPtyProcess(
                command=command,
                cwd=cwd,
                env=env,
                columns=columns,
                lines=lines,
                on_output=on_output,
            )
        except Exception:
            # Fall back to pipe-based process if winpty fails
            return PipeFallbackProcess(
                command=command,
                cwd=cwd,
                env=env,
                on_output=on_output,
            )
    else:
        try:
            return UnixPtyProcess(
                command=command,
                cwd=cwd,
                env=env,
                columns=columns,
                lines=lines,
                on_output=on_output,
            )
        except Exception:
            return PipeFallbackProcess(
                command=command,
                cwd=cwd,
                env=env,
                on_output=on_output,
            )
