"""Event-Driven Coordinator Alarm Pipeline & Intelligent Single-Thread Debounce Engine.

Monitors active worker terminal processes, detects transitions to interactive
IDLE prompts via a lightweight single-threaded debouncer without CPU exhaustion or
continuous timer thread churn, emits instant alarms to the Primary Coordinator
and MCP subscribers, and formats event summaries for terminal injection.
"""

from __future__ import annotations

from datetime import datetime
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

from mind.core.terminal_buffer import strip_ansi

if TYPE_CHECKING:
    from mind.core.terminal_manager import TerminalManager, WorkerSession


# ── Interactive IDLE Prompt Detection Patterns ─────────────────────────
# Matches common CLI prompts (agy, powershell, bash, zsh, cmd, textual inputs)
_PROMPT_PATTERNS = [
    re.compile(r"[❯»›>]\s*$", re.MULTILINE),                    # Shell / agy prompt ending with >, ❯, », ›
    re.compile(r"[$%#]\s*$", re.MULTILINE),                     # POSIX shell prompts ($, %, #)
    re.compile(r"\?\s*$", re.MULTILINE),                        # Interactive choice prompt ending in ?
    re.compile(r"^\s*\?\s+.*[:?]\s*$", re.MULTILINE),           # Inquirer / CLI query e.g. "? Select task to run: "
    re.compile(r"\([yY]/[nN]\)\s*$", re.MULTILINE),             # Yes/No confirmation prompt
    re.compile(r"(?:PS|cmd|bash|zsh|agy|mind)[^>\r\n]*>\s*$", re.IGNORECASE | re.MULTILINE), # Terminal prompts
    re.compile(r"(?:waiting for input|enter selection|ready)\b", re.IGNORECASE),
]


def is_idle_prompt(text: str) -> bool:
    """Check if the virtual terminal screen text ends with an interactive IDLE prompt.

    Strips ANSI color and control codes and inspects the trailing visible lines.
    Filters out statusline artifacts such as '-- INSERT --' and model names.
    """
    clean_text = strip_ansi(text).rstrip()
    if not clean_text:
        return False

    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    if not lines:
        return False

    # Ignore editor mode status lines like '-- INSERT --' or '-- NORMAL --'
    filtered_lines = [
        l for l in lines 
        if not re.match(r"^--\s*(?:INSERT|NORMAL|REPLACE|VISUAL)\b", l, re.IGNORECASE)
        and not re.match(r"^(?:Gemini|Claude|GPT|DeepSeek)\b.*?(?:high|low|medium)?$", l, re.IGNORECASE)
    ]
    if not filtered_lines:
        return False

    # Check last line
    last_line = filtered_lines[-1]
    for pattern in _PROMPT_PATTERNS:
        if pattern.search(last_line):
            return True

    # Check last two lines combined for multiline prompt setups
    if len(filtered_lines) >= 2:
        combined = f"{filtered_lines[-2]}\n{filtered_lines[-1]}"
        for pattern in _PROMPT_PATTERNS:
            if pattern.search(combined):
                return True

    return False


def extract_status_summary(worker: WorkerSession) -> str:
    """Extract a concise human-readable summary of the last action from worker buffer.

    Inspects the last non-empty lines before the prompt to determine the completed task
    or outcome (e.g. test results, build completion, or error message).
    """
    try:
        text = worker.buffer.get_screen_text(lines=15)
    except Exception:
        text = ""

    clean_text = strip_ansi(text).rstrip()
    if not clean_text:
        return f"{worker.name} finished execution and is IDLE at terminal prompt."

    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    # Remove trailing prompt lines to uncover the actual result
    while lines and is_idle_prompt(lines[-1]):
        lines.pop()

    if lines:
        last_meaningful = lines[-1]
        # Clean redundant formatting or leading bullets
        last_meaningful = re.sub(r"^[\s\-*#>\s]+", "", last_meaningful).strip()
        if len(last_meaningful) > 120:
            last_meaningful = last_meaningful[:117] + "..."
        if last_meaningful:
            return f"{worker.name}: {last_meaningful}"

    return f"{worker.name} finished execution and is IDLE at terminal prompt."


# ── Primary Coordinator Alarm Pipeline ──────────────────────────────────

class CoordinatorAlarmPipeline:
    """Event-Driven Primary Coordinator Alarm Pipeline.

    Uses a single background daemon thread with condition/event waiting to
    monitor all workers, debounce terminal settling without spinning or thread churn,
    detect transitions to IDLE prompts, and dispatch instant wake-up alarms to
    the Primary Coordinator.
    """

    def __init__(
        self,
        manager: TerminalManager | None = None,
        debounce_interval: float = 1.0,
    ) -> None:
        self._manager = manager
        self._debounce_interval = max(0.2, float(debounce_interval))
        self._pending_workers: dict[str, float] = {}  # worker_id -> last_activity_time
        self._alarms: list[dict[str, Any]] = []
        self._alarm_listeners: list[Callable[[dict[str, Any]], None]] = []

        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()

        self._thread: threading.Thread | None = None
        self._start_thread()

    def _start_thread(self) -> None:
        """Start the single background debounce thread."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._debounce_loop,
                    name="PrimaryCoordinatorAlarmPipeline",
                    daemon=True,
                )
                self._thread.start()

    def record_activity(self, worker: WorkerSession) -> None:
        """Notify the pipeline of output/activity on a worker terminal.

        Updates the debounce deadline and wakes the single background thread.
        """
        from mind.core.terminal_manager import WorkerProcessState

        worker_id = str(worker.worker_id)
        with self._lock:
            self._pending_workers[worker_id] = time.time()
            worker.state = WorkerProcessState.RUNNING

        # Wake the pipeline thread immediately to update its sleep schedule
        self._wake_event.set()

    def _get_worker(self, worker_id: str) -> WorkerSession | None:
        """Retrieve worker session through manager if available."""
        if self._manager is not None:
            return self._manager.get_worker(worker_id)
        return None

    def _debounce_loop(self) -> None:
        """Single-threaded event-driven debounce loop.

        Waits efficiently on an event with timeout equal to the minimum remaining
        debounce window across all pending workers. Consumes 0% CPU when no workers
        are active.
        """
        from mind.core.terminal_manager import WorkerProcessState

        while not self._stop_event.is_set():
            now = time.time()
            workers_to_fire: list[tuple[str, WorkerSession]] = []
            min_remaining: float | None = None

            with self._lock:
                pending_items = list(self._pending_workers.items())
                for worker_id, last_time in pending_items:
                    elapsed = now - last_time
                    if elapsed >= self._debounce_interval:
                        del self._pending_workers[worker_id]
                        worker = self._get_worker(worker_id)
                        if worker is not None and worker.is_alive:
                            workers_to_fire.append((worker_id, worker))
                    else:
                        remaining = self._debounce_interval - elapsed
                        if min_remaining is None or remaining < min_remaining:
                            min_remaining = remaining

            # Process workers whose debounce period has elapsed
            for worker_id, worker in workers_to_fire:
                # Transition worker to WAITING_INPUT
                worker.state = WorkerProcessState.WAITING_INPUT
                # Trigger worker-specific idle callbacks
                worker._notify_idle()

                # Dispatch coordinator alarm if this is a subordinate worker
                if worker.role != "coordinator" and str(worker.worker_id).lower() not in ("coordinator", "primary"):
                    summary = extract_status_summary(worker)
                    self.notify_worker_idle(worker_id=worker_id, summary=summary)

            # Wait on event until next debounce deadline or new activity arrives
            timeout = min_remaining if min_remaining is not None else None
            if timeout is not None:
                timeout = max(0.01, min(timeout, 5.0))

            self._wake_event.wait(timeout=timeout)
            self._wake_event.clear()

    # ── Coordinator Alarm Dispatch & Management ────────────────────────

    def add_alarm_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for coordinator wake-up alarm events."""
        with self._lock:
            if listener not in self._alarm_listeners:
                self._alarm_listeners.append(listener)

    def remove_alarm_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Unregister an alarm listener callback."""
        with self._lock:
            if listener in self._alarm_listeners:
                self._alarm_listeners.remove(listener)

    def emit_alarm(self, event: dict[str, Any]) -> None:
        """Emit an alarm/event to wake up the Primary Coordinator and notify subscribers."""
        with self._lock:
            self._alarms.append(event)
            listeners = list(self._alarm_listeners)

        for listener in listeners:
            try:
                listener(event)
            except Exception:
                pass

    def notify_worker_idle(self, worker_id: str, summary: str = "") -> dict[str, Any]:
        """Dispatch worker task completion / idle prompt alarm to Primary Coordinator."""
        worker = self._get_worker(worker_id)
        name = worker.name if worker else f"Worker-{worker_id}"

        if not summary:
            if worker:
                summary = extract_status_summary(worker)
            else:
                summary = f"{name} finished execution and is IDLE at terminal prompt."

        badge = f"⚡ Worker-{worker_id} Finished (Idle)"
        event = {
            "type": "worker_idle",
            "worker_id": str(worker_id),
            "name": name,
            "summary": summary,
            "badge": badge,
            "timestamp": datetime.now().isoformat(),
        }

        self.emit_alarm(event)
        return event

    def notify_worker_help(
        self,
        worker_id: str,
        reason: str = "",
        priority: str = "high",
    ) -> dict[str, Any]:
        """Dispatch urgent assistance alarm to Primary Coordinator from a worker agent."""
        worker = self._get_worker(worker_id)
        name = worker.name if worker else f"Worker-{worker_id}"

        badge = "🚨 Assistance Needed"
        event = {
            "type": "worker_help",
            "worker_id": str(worker_id),
            "name": name,
            "reason": reason or f"{name} encountered an obstacle and requests assistance.",
            "priority": priority,
            "badge": badge,
            "timestamp": datetime.now().isoformat(),
        }

        self.emit_alarm(event)
        return event

    def inject_event_to_coordinator(
        self,
        event: dict[str, Any],
        press_enter: bool = True,
    ) -> bool:
        """Inject formatted event summary into the Primary Coordinator terminal.

        Wakes up the coordinator to perform reasoning and execute next workflow steps
        only upon actual task completion.
        """
        if self._manager is None:
            return False

        coord_session = self._manager.get_worker("coordinator")
        if not coord_session or not coord_session.is_alive:
            return False

        event_type = event.get("type", "worker_idle")
        worker_id = event.get("worker_id", "")
        summary = event.get("summary") or event.get("reason", "")

        if event_type == "worker_idle":
            status_line = (
                f"\n[⚡ Worker-{worker_id} Finished (Idle)]: {summary}\n"
                f"Coordinator Directive: Worker task is complete. Deduce next workflow step and dispatch new task.\n"
            )
        else:
            priority = event.get("priority", "high")
            status_line = (
                f"\n[🚨 Assistance Needed from Worker-{worker_id} | Priority: {priority.upper()}]: {summary}\n"
                f"Coordinator Directive: Intervene immediately to resolve roadblock.\n"
            )

        coord_session.write(status_line, press_enter=press_enter)
        return True

    def get_alarms(self) -> list[dict[str, Any]]:
        """Return all queued coordinator alarm events."""
        with self._lock:
            return list(self._alarms)

    def clear_alarms(self) -> None:
        """Clear all coordinator alarm events."""
        with self._lock:
            self._alarms.clear()

    def stop(self, timeout: float = 1.0) -> None:
        """Cleanly stop the background debounce thread."""
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            self._thread = None
