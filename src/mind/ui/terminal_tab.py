"""Interactive Terminal Tab widget for Textual TUI.

Hosts a real PTY session running agy (or shell), renders the virtual screen
buffer with full ANSI styles, captures user keystrokes for direct interactive
control, and displays visual toast badges upon MCP directive injections.
"""

from __future__ import annotations

import sys
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Static

from mind.core.terminal_manager import WorkerProcessState, WorkerSession


# ANSI escape sequences for key combinations
_SPECIAL_KEYS: dict[str, str] = {
    "enter": "\r\n" if sys.platform == "win32" else "\r",
    "backspace": "\x08" if sys.platform == "win32" else "\x7f",
    "tab": "\t",
    "escape": "\x1b",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "delete": "\x1b[3~",
    "ctrl+c": "\x03",
    "ctrl+d": "\x04",
    "ctrl+z": "\x1a",
    "ctrl+l": "\x0c",
    "ctrl+a": "\x01",
    "ctrl+e": "\x05",
    "ctrl+u": "\x15",
    "ctrl+k": "\x0b",
    "ctrl+w": "\x17",
}


class TerminalScreenWidget(Widget):
    """The interactive terminal screen pane within a worker tab.

    Can be focused to capture raw keystrokes and type directly into agy.
    Renders the live ANSI screen buffer.
    """

    can_focus = True

    def __init__(self, worker_session: WorkerSession, **kwargs) -> None:
        super().__init__(**kwargs)
        self.worker_session = worker_session
        self._last_rendered_version = -1
        self.add_class("terminal-screen")

    def render(self):
        """Render the 2D virtual screen buffer with ANSI styles and cursor."""
        return self.worker_session.buffer.get_rich_text(show_cursor=self.has_focus)

    def on_mount(self) -> None:
        """Set up a high-frequency polling timer for smooth screen updates."""
        self.set_interval(0.04, self._check_for_updates)

    def _check_for_updates(self) -> None:
        """Trigger a re-render if new output arrived in the buffer."""
        current_version = self.worker_session.buffer.version
        if current_version != self._last_rendered_version:
            self._last_rendered_version = current_version
            self.refresh()

    def on_resize(self, event: events.Resize) -> None:
        """Sync virtual screen buffer and PTY dimensions with widget size."""
        cols = max(30, event.size.width - 2)
        rows = max(5, event.size.height - 2)
        self.worker_session.buffer.resize(columns=cols, lines=rows)
        if self.worker_session.process:
            self.worker_session.process.resize(columns=cols, lines=rows)

    def on_key(self, event: events.Key) -> None:
        """Handle keystrokes and deliver directly to the worker process."""
        key_name = event.key.lower()

        # Check special key mappings
        if key_name in _SPECIAL_KEYS:
            self.worker_session.write(_SPECIAL_KEYS[key_name])
            event.stop()
            event.prevent_default()
            return

        # Regular characters
        if event.character:
            self.worker_session.write(event.character)
            event.stop()
            event.prevent_default()


class WorkerTerminalTab(Widget):
    """Container tab hosting an individual worker agent's terminal session."""

    has_unread: reactive[bool] = reactive(False)

    def __init__(self, worker_session: WorkerSession, **kwargs) -> None:
        super().__init__(**kwargs)
        self.worker_session = worker_session
        self.screen_widget = TerminalScreenWidget(worker_session=worker_session)
        self._toast_timer = None
        self.add_class("worker-terminal-tab")

    def compose(self) -> ComposeResult:
        # 1. Top status line
        with Horizontal(classes="terminal-header"):
            yield Static(self._build_header_text(), id=f"header-text-{self.worker_session.worker_id}")

        # 2. Toast banner for inter-agent injections
        with Vertical(classes="terminal-toast", id=f"toast-{self.worker_session.worker_id}"):
            yield Static("", id=f"toast-text-{self.worker_session.worker_id}")

        # 3. Interactive terminal screen
        yield self.screen_widget

        # 4. Quick action helper bar
        with Horizontal(classes="terminal-controls"):
            yield Static(
                "[bold cyan]Click / Tab[/] Type in agy  ·  "
                "[bold red]Ctrl+C[/] Interrupt  ·  "
                "[dim]MCP Bridge: Active (http://127.0.0.1:8765/sse)[/]",
                classes="terminal-helper-text",
            )

    def on_mount(self) -> None:
        """Register notification listener with worker session."""
        self.worker_session.add_notification_listener(self._on_notification)
        self.set_interval(1.0, self._refresh_header)

    def _build_header_text(self) -> str:
        """Construct the styled header bar text."""
        state = self.worker_session.state
        if state == WorkerProcessState.RUNNING:
            state_str = "[bold green]● RUNNING[/]"
        elif state == WorkerProcessState.PAUSED:
            state_str = "[bold yellow]⏸ PAUSED[/]"
        elif state == WorkerProcessState.WAITING_INPUT:
            state_str = "[bold blue]⏳ WAITING INPUT[/]"
        else:
            state_str = "[bold red]❌ TERMINATED[/]"

        pid_info = f"PID: {self.worker_session.pid}" if self.worker_session.pid else "PID: -"
        badge = ""
        if self.worker_session.unread_notifications > 0:
            badge = f"  [bold red on white] 🔔 {self.worker_session.unread_notifications} NEW DIRECTIVE [/]"

        return (
            f" [bold cyan]{self.worker_session.name}[/] "
            f"[dim]({self.worker_session.model} · {pid_info})[/] "
            f"{state_str}{badge} "
            f"[dim italic]— {self.worker_session.task}[/]"
        )

    def _refresh_header(self) -> None:
        """Periodically update header text."""
        try:
            widget = self.query_one(f"#header-text-{self.worker_session.worker_id}", Static)
            widget.update(self._build_header_text())
        except Exception:
            pass

    def _on_notification(self, session: WorkerSession, formatted_directive: str) -> None:
        """Handle incoming interrupt/injection event from MCP or coordinator."""
        self.app.call_from_thread(self._show_toast, formatted_directive)

    def _show_toast(self, message: str) -> None:
        """Display an immediate visual toast notification banner inside the tab."""
        self.has_unread = True
        self._refresh_header()

        try:
            toast_box = self.query_one(f"#toast-{self.worker_session.worker_id}", Vertical)
            toast_text = self.query_one(f"#toast-text-{self.worker_session.worker_id}", Static)
            toast_text.update(f"[bold yellow]⚡ INCOMING DIRECTIVE INJECTED VIA MCP:[/]\n{message.strip()}")
            toast_box.add_class("visible")

            # Auto-dismiss banner after 8 seconds
            if self._toast_timer:
                self._toast_timer.stop()
            self._toast_timer = self.set_timer(8.0, self._hide_toast)
        except Exception:
            pass

    def _hide_toast(self) -> None:
        """Hide the toast notification banner."""
        try:
            toast_box = self.query_one(f"#toast-{self.worker_session.worker_id}", Vertical)
            toast_box.remove_class("visible")
        except Exception:
            pass

    def on_click(self) -> None:
        """Focus the terminal screen on tab click and clear unread badge."""
        self.screen_widget.focus()
        if self.worker_session.unread_notifications > 0:
            self.worker_session.clear_notifications()
            self._refresh_header()
