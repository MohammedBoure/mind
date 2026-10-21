"""Terminal Manager and Worker Session orchestrator for the mind TUI.

Coordinates cross-platform PTY worker processes (running agy instances),
maintains thread-safe terminal buffers, handles inter-agent interrupt directives,
and exposes worker statuses to the embedded MCP server and Textual UI.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time
from typing import Any, Callable

from mind.core.credentials import (
    CrossProcessCredentialLock,
    get_slot_token_path,
    restore_slot_credential,
    setup_slot_env,
    sync_slot_credential_from_system,
)
from mind.core.directives import load_directive, save_directive
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
    assigned_agent: str = ""
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
        assigned_agent: str = "",
        columns: int = 80,
        lines: int = 24,
    ) -> None:
        self.worker_id = worker_id
        self.agent_id = agent_id or worker_id
        self.name = name or f"Worker-{worker_id}"
        self.role = role
        self.model = model
        self.task = task or "Idle - Standing by for directives"
        self.cli_mode = cli_mode
        self.reasoning_effort = reasoning_effort
        self.extra_flags = extra_flags
        # Determine default assigned_agent if not provided
        if not assigned_agent:
            if str(worker_id).isdigit():
                assigned_agent = f"agy{worker_id}"
            elif str(worker_id).lower() in ("coordinator", "primary") or role == "coordinator":
                assigned_agent = "agy1"
            elif name and name.lower().startswith("agy"):
                assigned_agent = name.lower()
            elif name and "worker-" in name.lower():
                m = re.search(r"\d+", name)
                if m:
                    assigned_agent = f"agy{m.group()}"

        self.assigned_agent = assigned_agent or (name if name and name.startswith("agy") else "")
        if not instructions:
            target_key = self.assigned_agent or ("coordinator" if self.role == "coordinator" else f"agy{self.worker_id}")
            self.instructions = load_directive(target_key)
        else:
            self.instructions = instructions
        self.created_at = datetime.now()
        self.runtime_warnings: list[str] = []

        # Parse and store custom CLI startup arguments
        self.custom_cli_args: list[str] = []
        if self.extra_flags:
            import shlex
            try:
                self.custom_cli_args = shlex.split(self.extra_flags)
            except Exception:
                self.custom_cli_args = self.extra_flags.split()

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
            assigned_agent=self.assigned_agent,
            instructions=self.instructions,
        )

        self._last_output_time: float = time.time()
        self._idle_check_timer: threading.Timer | None = None
        self._output_listeners: list[Callable[[str], None]] = []
        self._notification_listeners: list[Callable[[WorkerSession, str], None]] = []
        self._idle_listeners: list[Callable[[WorkerSession], None]] = []
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

    def add_idle_listener(self, listener: Callable[[WorkerSession], None]) -> None:
        """Register a callback for when worker transitions to idle prompt."""
        with self._lock:
            self._idle_listeners.append(listener)

    def _check_idle_state(self) -> None:
        """Transition process to waiting_input and notify listeners when terminal settles."""
        if not self.is_alive:
            return
        time_since_output = time.time() - self._last_output_time
        if time_since_output < 1.1:
            remaining = max(0.2, 1.2 - time_since_output)
            with self._lock:
                self._idle_check_timer = threading.Timer(remaining, self._check_idle_state)
                self._idle_check_timer.daemon = True
                self._idle_check_timer.start()
            return

        if self.state == WorkerProcessState.RUNNING:
            self.state = WorkerProcessState.WAITING_INPUT
            with self._lock:
                listeners = list(self._idle_listeners)
            for listener in listeners:
                try:
                    listener(self)
                except Exception:
                    pass

    def _on_process_output(self, chunk: str) -> None:
        """Receive output chunk from PTY process and update buffer/listeners."""
        self.buffer.feed(chunk)
        self._last_output_time = time.time()
        self.state = WorkerProcessState.RUNNING

        # Debounced check for terminal idle state without thread churn
        with self._lock:
            if self._idle_check_timer is None or not self._idle_check_timer.is_alive():
                self._idle_check_timer = threading.Timer(1.2, self._check_idle_state)
                self._idle_check_timer.daemon = True
                self._idle_check_timer.start()

        # Detect runtime warnings from stderr/stdout (e.g. --effort fallback, unknown agent)
        chunk_lower = chunk.lower()
        if "warning" in chunk_lower or "unknown agent" in chunk_lower or "fallback" in chunk_lower:
            import re
            for line in chunk.splitlines():
                l_lower = line.lower()
                if "warning" in l_lower or "fallback" in l_lower or "unknown agent" in l_lower:
                    clean_line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", line).strip()
                    if clean_line and clean_line not in self.runtime_warnings:
                        self.runtime_warnings.append(clean_line[:80])
                        if len(self.runtime_warnings) > 5:
                            self.runtime_warnings.pop(0)

        with self._lock:
            listeners = list(self._output_listeners)
        for listener in listeners:
            try:
                listener(chunk)
            except Exception:
                pass

    def get_slot_id(self) -> int | None:
        """Derive slot number (1..20) for this session to isolate credentials."""
        target = self.assigned_agent or self.name or str(self.worker_id)
        if "coordinator" in target.lower() or str(self.worker_id).lower() in ("coordinator", "primary"):
            if self.assigned_agent:
                m = re.search(r"\d+", self.assigned_agent)
                if m:
                    return int(m.group())
            return 1
        m = re.search(r"\d+", target)
        if m:
            return int(m.group())
        return None

    def start(
        self,
        command: str | list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Launch the worker agent process inside a cross-platform PTY with slot isolation."""
        if self.process and self.process.is_alive():
            return

        self.custom_command = command
        self.last_cwd = cwd or self.last_cwd or os.getcwd()

        # Set up isolated environment variables and verify token persistence
        slot = self.get_slot_id()
        base = env if env is not None else (self.last_env or os.environ)
        worker_env = dict(base)
        if slot:
            worker_env = setup_slot_env(slot, base_env=worker_env)

        self.last_env = worker_env
        resolved_command = self._resolve_command(command)

        if slot:
            with CrossProcessCredentialLock():
                # 1. Restore the slot's token into system credential manager / keyring under lock
                restore_slot_credential(slot)
                # 2. Spawn the PTY process under the lock
                self.process = spawn_pty(
                    command=resolved_command,
                    cwd=self.last_cwd,
                    env=self.last_env,
                    columns=self.buffer.columns,
                    lines=self.buffer.lines,
                    on_output=self._on_process_output,
                )
                # 3. Hold lock for 800ms so agy process boots and loads credentials before next slot
                time.sleep(0.8)
                # 4. Sync any newly refreshed token back to slot storage
                sync_slot_credential_from_system(slot)
        else:
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
                import shlex
                try:
                    self.custom_cli_args = shlex.split(self.extra_flags) if self.extra_flags else []
                except Exception:
                    self.custom_cli_args = self.extra_flags.split() if self.extra_flags else []
            if "custom_cli_args" in new_config and new_config["custom_cli_args"]:
                self.custom_cli_args = list(new_config["custom_cli_args"])
            if "instructions" in new_config:
                self.instructions = new_config["instructions"]
                self.profile.instructions = new_config["instructions"]
            if "assigned_agent" in new_config:
                self.assigned_agent = new_config["assigned_agent"]
                self.profile.assigned_agent = new_config["assigned_agent"]
            if "task" in new_config and new_config["task"]:
                self.task = new_config["task"]

        # 1. Terminate old process
        self.terminate()

        # 2. Reset virtual terminal screen buffer
        self.buffer.clear()
        self.unread_notifications = 0
        self.runtime_warnings.clear()

        # 3. Respawn with updated command or flags
        target_command = command if command is not None else self.custom_command
        self.start(command=target_command, cwd=self.last_cwd, env=self.last_env)

    def _resolve_command(self, command: str | list[str] | None) -> list[str]:
        """Resolve executable command, defaulting to `agy` with tuned CLI flags if present."""
        if command:
            if isinstance(command, str):
                return command.split()
            return list(command)

        # 1. Search for standard `agy` or `agy.exe` on PATH or LocalAppData
        # Running agy directly avoids nested cmd/python wrapper delays and lock contention
        agy_path = shutil.which("agy") or shutil.which("agy.exe")
        if not agy_path and sys.platform == "win32":
            local_agy = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
            if os.path.exists(local_agy):
                agy_path = local_agy

        # 2. Check if assigned_agent has an explicit executable launcher (e.g. agy1.cmd) fallback
        agent_launcher = None
        target_agent = self.assigned_agent
        if not target_agent:
            slot = self.get_slot_id()
            if slot:
                target_agent = f"agy{slot}"

        if target_agent and not agy_path:
            agent_launcher = shutil.which(target_agent) or shutil.which(f"{target_agent}.cmd")
            if not agent_launcher and sys.platform == "win32":
                local_cmd = os.path.expandvars(rf"%LOCALAPPDATA%\agy\bin\{target_agent}.cmd")
                if os.path.exists(local_cmd):
                    agent_launcher = local_cmd

        target_bin = agy_path or agent_launcher

        if target_bin:
            cmd = [target_bin]
            # If invoking standard agy and a custom agent was selected (not a slot like agy1), pass --agent
            if agy_path and self.assigned_agent and not re.match(r"^agy\d+$", self.assigned_agent, re.IGNORECASE):
                cmd.extend(["--agent", self.assigned_agent])
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
            if self.process is None:
                self.start()
                time.sleep(0.3)
            else:
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

    async def interrupt_and_inject_async(
        self,
        sender_id: str,
        message: str,
        priority: str = "high",
    ) -> str:
        """Asynchronously send SIGINT/Ctrl+C to halt current execution, wait for prompt, and inject message."""
        if not self.process or not self.process.is_alive():
            if self.process is None:
                self.start()
                await asyncio.sleep(0.3)
            else:
                return f"Error: Worker {self.worker_id} process is not running."

        # 1. Send interrupt signal
        self.process.send_interrupt()
        self.state = WorkerProcessState.PAUSED

        # 2. Wait for terminal prompt to stabilize asynchronously without blocking event loop
        await asyncio.sleep(0.4)

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
            "custom_cli_args": self.custom_cli_args,
            "behavioral_flags": self.custom_cli_args,
            "assigned_agent": self.assigned_agent,
            "runtime_warnings": list(self.runtime_warnings),
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
        self._coordinator_alarms: list[dict[str, Any]] = []
        self._alarm_listeners: list[Callable[[dict[str, Any]], None]] = []

    def add_alarm_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Register a listener for coordinator wake-up alarm events."""
        with self._lock:
            self._alarm_listeners.append(listener)

    def emit_coordinator_alarm(self, event: dict[str, Any]) -> None:
        """Emit an alarm/event to wake up the Primary Coordinator and notify subscribers."""
        with self._lock:
            self._coordinator_alarms.append(event)
            listeners = list(self._alarm_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                pass

    def get_coordinator_alarms(self) -> list[dict[str, Any]]:
        """Return all recorded coordinator alarms and event triggers."""
        with self._lock:
            return list(self._coordinator_alarms)

    def clear_coordinator_alarms(self) -> None:
        """Clear the coordinator alarm queue."""
        with self._lock:
            self._coordinator_alarms.clear()

    def notify_coordinator_worker_idle(self, worker_id: str, status_summary: str = "") -> dict[str, Any]:
        """Record worker task completion / idle prompt detection and emit alarm event."""
        worker = self.get_worker(worker_id)
        name = worker.name if worker else f"Worker-{worker_id}"
        event = {
            "type": "worker_idle",
            "worker_id": str(worker_id),
            "name": name,
            "summary": status_summary or f"{name} finished execution and is IDLE at terminal prompt.",
            "timestamp": datetime.now().isoformat(),
        }
        self.emit_coordinator_alarm(event)
        return event

    def notify_coordinator_worker_help(
        self,
        worker_id: str,
        reason: str = "",
        priority: str = "high",
    ) -> dict[str, Any]:
        """Record a worker assistance request and emit priority alarm event."""
        worker = self.get_worker(worker_id)
        name = worker.name if worker else f"Worker-{worker_id}"
        event = {
            "type": "worker_help",
            "worker_id": str(worker_id),
            "name": name,
            "reason": reason or f"{name} encountered an obstacle and requests assistance.",
            "priority": priority,
            "timestamp": datetime.now().isoformat(),
        }
        self.emit_coordinator_alarm(event)
        return event

    def _on_worker_idle_detected(self, worker: WorkerSession) -> None:
        """Internal callback fired when a worker PTY process settles to idle prompt."""
        if worker.role == "coordinator" or str(worker.worker_id).lower() in ("coordinator", "primary"):
            return
        self.notify_coordinator_worker_idle(worker.worker_id)

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
        assigned_agent: str = "",
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

            # Automatically deduce assigned_agent slot if not provided
            if not assigned_agent:
                if str(worker_id).isdigit():
                    assigned_agent = f"agy{worker_id}"
                elif str(worker_id).lower() in ("coordinator", "primary") or role == "coordinator":
                    assigned_agent = "agy1"
                elif name and name.lower().startswith("agy"):
                    assigned_agent = name.lower()
                elif name and "worker-" in name.lower():
                    m = re.search(r"\d+", name)
                    if m:
                        assigned_agent = f"agy{m.group()}"

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
                assigned_agent=assigned_agent,
                columns=columns,
                lines=lines,
            )
            session.add_notification_listener(self._on_worker_notification)
            session.add_idle_listener(self._on_worker_idle_detected)
            self._workers[worker_id] = session

        if autostart:
            session.start(command=command, cwd=cwd)

        return session

    def restart_worker(
        self,
        worker_id: str,
        new_args: dict[str, Any] | list[str] | str | None = None,
        command: str | list[str] | None = None,
        **kwargs: Any,
    ) -> WorkerSession | None:
        """Find and cleanly restart an active worker session with updated configuration or CLI arguments.
        
        Args:
            worker_id: The ID of the worker to restart.
            new_args: Configuration dict, list of CLI args, or extra flags string.
            command: Explicit replacement command line (optional).
            **kwargs: Extra configuration keys (e.g. model, cli_mode, reasoning_effort).
        """
        worker = self.get_worker(worker_id)
        if not worker:
            return None

        cfg: dict[str, Any] = {}
        cmd: str | list[str] | None = command

        if isinstance(new_args, dict):
            cfg.update(new_args)
        elif isinstance(new_args, (list, tuple)):
            cmd = list(new_args)
        elif isinstance(new_args, str):
            cfg["extra_flags"] = new_args

        if kwargs:
            cfg.update(kwargs)

        worker.restart(new_config=cfg or None, command=cmd)
        return worker

    def get_worker(self, worker_id: str) -> WorkerSession | None:
        """Find a worker session by ID, name, or normalized identifier."""
        target = str(worker_id).strip()
        with self._lock:
            # 1. Exact match
            if target in self._workers:
                return self._workers[target]
            # 2. Case-insensitive / role / prefix matching
            target_lower = target.lower()
            if target_lower in ("coordinator", "primary"):
                for key, w in self._workers.items():
                    if key.lower() in ("coordinator", "primary") or w.role == "coordinator":
                        return w
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

    def discover_system_agents(self) -> list[str]:
        """Discover all available agy agents registered on the host system."""
        from mind.core.agent_discovery import discover_system_agents
        return discover_system_agents()

    def discover_agent_slots(self) -> list[Any]:
        """Discover all available agy agents and their slot isolation metadata."""
        from mind.core.agent_discovery import discover_agent_slots
        return discover_agent_slots()

    def stop_all(self) -> None:
        """Terminate all worker processes."""
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.terminate()
