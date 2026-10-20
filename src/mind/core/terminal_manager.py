"""Terminal Manager and Worker Session orchestrator for the mind TUI.

Coordinates cross-platform PTY worker processes (running agy instances),
maintains thread-safe terminal buffers, handles inter-agent interrupt directives,
and exposes worker statuses to the embedded MCP server and Textual UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from typing import Any, Callable

from mind.core.pty_process import BasePtyProcess, spawn_pty
from mind.core.terminal_buffer import TerminalBuffer


class WorkerProcessState(str, Enum):
    """Operational states of a worker agent process."""
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_INPUT = "waiting_input"
    TERMINATED = "terminated"


@dataclass
class AgentProfile:
    """Configuration profile and behavioral instructions for an agent."""
    agent_id: str
    role: str = "worker"
    model: str = "gemini-3.8-flash-high"
    cli_mode: str = "auto"
    reasoning_effort: str = "high"
    extra_flags: str = ""
    principles: list[str] = field(
        default_factory=lambda: [
            "Execute tasks assigned by the primary coordinator.",
            "Report progress and roadblocks immediately.",
            "Prioritize interrupt directives from supervisor and peer agents.",
            "Maintain clean, deterministic workspace edits.",
        ]
    )
    instructions: str = "Act as an autonomous worker agent. Listen for directives and execute terminal tasks."
    local_config: dict[str, Any] = field(default_factory=dict)


class WorkerSession:
    """Manages an individual worker agent's terminal process and screen buffer."""

    def __init__(
        self,
        worker_id: str,
        agent_id: str | None = None,
        name: str | None = None,
        role: str = "worker",
        model: str = "gemini-3.8-flash-high",
        task: str = "",
        cli_mode: str = "auto",
        reasoning_effort: str = "high",
        extra_flags: str = "",
        instructions: str = "",
        columns: int = 80,
        lines: int = 24,
    ) -> None:
        self.worker_id = worker_id
        self.agent_id = agent_id or worker_id
        self.name = name or f"Worker-{worker_id}"
        self.role = role
        self.model = model
        self.task = task or "Awaiting task assignment"
        self.cli_mode = cli_mode
        self.reasoning_effort = reasoning_effort
        self.extra_flags = extra_flags
        self.instructions = instructions or "Act as an autonomous worker agent. Listen for directives and execute terminal tasks."
        self.created_at = datetime.now()

        self.buffer = TerminalBuffer(columns=columns, lines=lines)
        self.process: BasePtyProcess | None = None
        self.state = WorkerProcessState.PAUSED
        self.unread_notifications = 0
        self.last_interrupt_directive: str | None = None
        self.custom_command: str | list[str] | None = None
        self.last_cwd: str | None = None
        self.last_env: dict[str, str] | None = None

        self.profile = AgentProfile(
            agent_id=self.agent_id,
            role=self.role,
            model=self.model,
            cli_mode=self.cli_mode,
            reasoning_effort=self.reasoning_effort,
            extra_flags=self.extra_flags,
            instructions=self.instructions,
        )

        self._output_listeners: list[Callable[[str], None]] = []
        self._notification_listeners: list[Callable[[WorkerSession, str], None]] = []
        self._lock = threading.Lock()

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    @property
    def is_alive(self) -> bool:
        return self.process.is_alive() if self.process else False

    def add_output_listener(self, listener: Callable[[str], None]) -> None:
        """Register a callback for raw output bytes."""
        with self._lock:
            self._output_listeners.append(listener)

    def add_notification_listener(self, listener: Callable[[WorkerSession, str], None]) -> None:
        """Register a callback for interrupt injection toasts/events."""
        with self._lock:
            self._notification_listeners.append(listener)

    def _on_process_output(self, chunk: str) -> None:
        """Receive output chunk from PTY process and update buffer/listeners."""
        self.buffer.feed(chunk)
        with self._lock:
            listeners = list(self._output_listeners)
        for listener in listeners:
            try:
                listener(chunk)
            except Exception:
                pass

    def start(
        self,
        command: str | list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Launch the worker agent process inside a cross-platform PTY."""
        if self.process and self.process.is_alive():
            return

        self.custom_command = command
        self.last_cwd = cwd or self.last_cwd or os.getcwd()
        self.last_env = env if env is not None else self.last_env

        resolved_command = self._resolve_command(command)
        self.process = spawn_pty(
            command=resolved_command,
            cwd=self.last_cwd,
            env=self.last_env,
            columns=self.buffer.columns,
            lines=self.buffer.lines,
            on_output=self._on_process_output,
        )
        self.state = WorkerProcessState.RUNNING

    def restart(
        self,
        new_config: dict[str, Any] | None = None,
        command: str | list[str] | None = None,
    ) -> None:
        """Cleanly terminate old process, update configuration flags, and respawn worker PTY."""
        if new_config:
            if "name" in new_config and new_config["name"]:
                self.name = new_config["name"]
            if "role" in new_config and new_config["role"]:
                self.role = new_config["role"]
                self.profile.role = new_config["role"]
            if "model" in new_config and new_config["model"]:
                self.model = new_config["model"]
                self.profile.model = new_config["model"]
            if "cli_mode" in new_config and new_config["cli_mode"]:
                self.cli_mode = new_config["cli_mode"]
                self.profile.cli_mode = new_config["cli_mode"]
            if "reasoning_effort" in new_config and new_config["reasoning_effort"]:
                self.reasoning_effort = new_config["reasoning_effort"]
                self.profile.reasoning_effort = new_config["reasoning_effort"]
            if "extra_flags" in new_config:
                self.extra_flags = new_config["extra_flags"]
                self.profile.extra_flags = new_config["extra_flags"]
            if "instructions" in new_config:
                self.instructions = new_config["instructions"]
                self.profile.instructions = new_config["instructions"]
            if "task" in new_config and new_config["task"]:
                self.task = new_config["task"]

        # 1. Terminate old process
        self.terminate()

        # 2. Reset virtual terminal screen buffer
        self.buffer.clear()
        self.unread_notifications = 0

        # 3. Respawn with updated command or flags
        target_command = command if command is not None else self.custom_command
        self.start(command=target_command, cwd=self.last_cwd, env=self.last_env)

    def _resolve_command(self, command: str | list[str] | None) -> list[str]:
        """Resolve executable command, defaulting to `agy` with tuned CLI flags if present."""
        if command:
            if isinstance(command, str):
                return command.split()
            return list(command)

        # 1. Search for `agy` or `agy.exe` on PATH
        agy_path = shutil.which("agy") or shutil.which("agy.exe")

        # 2. Check standard Windows LocalAppData directory
        if not agy_path and sys.platform == "win32":
            local_agy = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
            if os.path.exists(local_agy):
                agy_path = local_agy

        if agy_path:
            cmd = [agy_path]
            if self.cli_mode:
                cmd.extend(["--mode", self.cli_mode])
            if self.model and self.model != "default":
                cmd.extend(["--model", self.model])
            if self.reasoning_effort:
                cmd.extend(["--effort", self.reasoning_effort])
            if self.extra_flags:
                import shlex
                try:
                    cmd.extend(shlex.split(self.extra_flags))
                except Exception:
                    cmd.extend(self.extra_flags.split())
            return cmd

        # Fallback to interactive shell
        if sys.platform == "win32":
            return ["powershell.exe", "-NoLogo"]
        return ["/bin/bash"]

    def write(self, text: str, press_enter: bool = False) -> None:
        """Send raw input or keystrokes to the worker process."""
        if not self.process:
            return

        payload = text
        if press_enter:
            payload += "\r\n" if sys.platform == "win32" else "\n"

        self.process.write(payload)

    def interrupt_and_inject(
        self,
        sender_id: str,
        message: str,
        priority: str = "high",
    ) -> str:
        """Send SIGINT/Ctrl+C to halt current execution, wait for prompt, and inject message."""
        if not self.process or not self.process.is_alive():
            return f"Error: Worker {self.worker_id} process is not running."

        # 1. Send interrupt signal
        self.process.send_interrupt()
        self.state = WorkerProcessState.PAUSED

        # 2. Wait for terminal prompt to stabilize
        time.sleep(0.4)

        # 3. Format injection payload
        formatted_directive = (
            f"\n[INTERRUPT from {sender_id} | Priority: {priority.upper()}]: {message}\n"
            f"Directive: Prioritize this message. Adjust plan and resume previous task only if no conflict.\n"
        )
        self.last_interrupt_directive = formatted_directive

        # 4. Inject directive into stdin
        self.write(formatted_directive, press_enter=True)
        self.state = WorkerProcessState.RUNNING

        # 5. Increment notification counter and trigger UI listeners
        self.unread_notifications += 1
        with self._lock:
            listeners = list(self._notification_listeners)
        for listener in listeners:
            try:
                listener(self, formatted_directive)
            except Exception:
                pass

        return f"Successfully interrupted {self.worker_id} and injected directive from {sender_id}."

    def clear_notifications(self) -> None:
        """Mark all incoming notifications as read."""
        self.unread_notifications = 0

    def get_screen(self, lines: int = 50) -> str:
        """Get recent lines of the terminal buffer."""
        return self.buffer.get_screen_text(lines=lines)

    def get_profile_dict(self) -> dict[str, Any]:
        """Inspect and return agent profile dictionary, including any local `./agent` config."""
        profile_data: dict[str, Any] = {
            "worker_id": self.worker_id,
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "model": self.model,
            "cli_mode": self.cli_mode,
            "reasoning_effort": self.reasoning_effort,
            "extra_flags": self.extra_flags,
            "task": self.task,
            "state": self.state.value,
            "pid": self.pid,
            "principles": self.profile.principles,
            "instructions": self.instructions or self.profile.instructions,
            "unread_notifications": self.unread_notifications,
        }

        # Check for local ./agent or .agent configuration file
        agent_dir = Path.cwd() / "agent"
        if agent_dir.exists() and agent_dir.is_dir():
            configs = [f.name for f in agent_dir.glob("*.json")] + [f.name for f in agent_dir.glob("*.yaml")]
            profile_data["local_agent_files"] = configs

        return profile_data

    def terminate(self) -> None:
        """Safely terminate the worker process."""
        self.state = WorkerProcessState.TERMINATED
        if self.process:
            self.process.terminate()
            self.process = None


# ── Global Terminal Manager Singleton ──────────────────────────────

class TerminalManager:
    """Central registry and manager for all active worker terminal sessions."""

    _instance: TerminalManager | None = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._workers: dict[str, WorkerSession] = {}
        self._lock = threading.Lock()
        self._global_notification_listeners: list[Callable[[WorkerSession, str], None]] = []

    @classmethod
    def get_instance(cls) -> TerminalManager:
        """Retrieve or initialize the global singleton instance."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = TerminalManager()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (terminates all workers)."""
        with cls._singleton_lock:
            if cls._instance is not None:
                cls._instance.stop_all()
                cls._instance = None

    def add_notification_listener(self, listener: Callable[[WorkerSession, str], None]) -> None:
        """Register a global listener for interrupt/injection events across all workers."""
        with self._lock:
            self._global_notification_listeners.append(listener)

    def _on_worker_notification(self, worker: WorkerSession, message: str) -> None:
        with self._lock:
            listeners = list(self._global_notification_listeners)
        for listener in listeners:
            try:
                listener(worker, message)
            except Exception:
                pass

    def create_worker(
        self,
        worker_id: str,
        agent_id: str | None = None,
        name: str | None = None,
        role: str = "worker",
        model: str = "gemini-3.8-flash-high",
        task: str = "",
        cli_mode: str = "auto",
        reasoning_effort: str = "high",
        extra_flags: str = "",
        instructions: str = "",
        command: str | list[str] | None = None,
        cwd: str | None = None,
        columns: int = 80,
        lines: int = 24,
        autostart: bool = True,
    ) -> WorkerSession:
        """Create, register, and optionally start a new worker terminal session."""
        with self._lock:
            if worker_id in self._workers:
                return self._workers[worker_id]

            session = WorkerSession(
                worker_id=worker_id,
                agent_id=agent_id,
                name=name,
                role=role,
                model=model,
                task=task,
                cli_mode=cli_mode,
                reasoning_effort=reasoning_effort,
                extra_flags=extra_flags,
                instructions=instructions,
                columns=columns,
                lines=lines,
            )
            session.add_notification_listener(self._on_worker_notification)
            self._workers[worker_id] = session

        if autostart:
            session.start(command=command, cwd=cwd)

        return session

    def restart_worker(
        self,
        worker_id: str,
        new_config: dict[str, Any] | None = None,
        command: str | list[str] | None = None,
    ) -> WorkerSession | None:
        """Find and restart an active worker session with optional new configuration."""
        worker = self.get_worker(worker_id)
        if not worker:
            return None
        worker.restart(new_config=new_config, command=command)
        return worker

    def get_worker(self, worker_id: str) -> WorkerSession | None:
        """Find a worker session by ID, name, or normalized identifier."""
        target = str(worker_id).strip()
        with self._lock:
            # 1. Exact match
            if target in self._workers:
                return self._workers[target]
            # 2. Case-insensitive / prefix matching
            target_lower = target.lower()
            target_norm = target_lower.replace("worker-", "").replace("worker_", "").replace("worker", "")
            for key, w in self._workers.items():
                if key.lower() == target_lower or w.name.lower() == target_lower:
                    return w
                key_norm = key.lower().replace("worker-", "").replace("worker_", "").replace("worker", "")
                if target_norm and key_norm == target_norm:
                    return w
            return None

    def list_workers(self) -> list[WorkerSession]:
        """Return all registered worker sessions."""
        with self._lock:
            return list(self._workers.values())

    def remove_worker(self, worker_id: str) -> None:
        """Terminate and remove a worker session."""
        with self._lock:
            session = self._workers.pop(str(worker_id), None)
        if session:
            session.terminate()

    def stop_all(self) -> None:
        """Terminate all worker processes."""
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.terminate()
