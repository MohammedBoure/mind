"""Agent log pane widget — displays a streaming log for one agent."""

from __future__ import annotations

from datetime import datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from mind.state.models import AgentInfo, AgentStatus, LogEntry
from mind.ui.clipboard import copy_to_clipboard


# Style classes per log entry type
_TYPE_CLASSES: dict[str, str] = {
    "thought": "log-thought",
    "tool_call": "log-tool-call",
    "result": "log-result",
    "error": "log-error",
    "info": "log-info",
}

# Status indicators
_STATUS_ICONS: dict[AgentStatus, str] = {
    AgentStatus.IDLE: "[dim]IDLE[/]",
    AgentStatus.THINKING: "[bold #a78bfa]THINKING[/]",
    AgentStatus.EXECUTING: "[bold #38bdf8]EXECUTING[/]",
    AgentStatus.RUNNING: "[bold #9ece6a]● RUNNING[/]",
    AgentStatus.WAITING: "[bold #fbbf24]WAITING[/]",
    AgentStatus.ERROR: "[bold #f87171]ERROR[/]",
}


class AgentLogPane(Widget):
    """Displays a scrollable log stream for a single agent.

    The pane includes a title bar with agent info and a scrollable
    region for log entries. Entries are color-coded by type.
    """

    def __init__(
        self,
        agent: AgentInfo,
        logs: list[LogEntry] | None = None,
        pane_id: str = "",
        **kwargs,
    ) -> None:
        super().__init__(id=pane_id or f"pane-agent-{agent.id}", **kwargs)
        self._agent = agent
        self._logs = logs or []
        self.add_class("agent-pane")

    def compose(self) -> ComposeResult:
        status_text = _STATUS_ICONS.get(self._agent.status, "●")
        title = (
            f" {self._agent.name} "
            f"[dim]({self._agent.model})[/] "
            f"{status_text} "
            f"[dim italic]— {self._agent.task}[/]"
        )
        yield Static(title, classes="pane-title-bar")

        with VerticalScroll(classes="log-view"):
            for entry in self._logs:
                yield Static(
                    _format_log_entry(entry),
                    classes=f"log-line {_TYPE_CLASSES.get(entry.entry_type, 'log-info')}",
                )

    def append_log(self, entry: LogEntry) -> None:
        """Append a new log entry to the pane and scroll to bottom."""
        self._logs.append(entry)
        log_view = self.query(".log-view")
        if log_view:
            scroll = log_view.first()
            widget = Static(
                _format_log_entry(entry),
                classes=f"log-line {_TYPE_CLASSES.get(entry.entry_type, 'log-info')}",
            )
            scroll.mount(widget)
            scroll.scroll_end(animate=False)

    def update_status(self, status: AgentStatus) -> None:
        """Update the agent status displayed in the title bar."""
        self._agent.status = status
        title_bars = self.query(".pane-title-bar")
        if title_bars:
            status_text = _STATUS_ICONS.get(status, "●")
            title = (
                f" {self._agent.name} "
                f"[dim]({self._agent.model})[/] "
                f"{status_text} "
                f"[dim italic]— {self._agent.task}[/]"
            )
            title_bars.first().update(title)

    def _get_safe_app(self) -> Any:
        try:
            return self.app
        except Exception:
            return None

    def copy_selection_or_buffer(self) -> str:
        """Copy all formatted log lines to system clipboard."""
        return self.copy_content()

    def copy_content(self) -> str:
        """Format and copy all logs in this pane to system clipboard."""
        if not self._logs:
            self._safe_notify("Log pane is empty", severity="warning")
            return ""

        plain_lines = []
        for e in self._logs:
            ts = e.timestamp.strftime("%H:%M:%S")
            plain_lines.append(f"[{ts}] [{e.entry_type.upper()}] {e.content}")

        text = "\n".join(plain_lines)
        copy_to_clipboard(text, app=self._get_safe_app())
        self._safe_notify(f"Copied {len(self._logs)} log lines to clipboard", timeout=1.5)
        return text

    def _safe_notify(self, message: str, severity: str = "information", timeout: float = 1.5) -> None:
        try:
            self.notify(message, severity=severity, timeout=timeout)
        except Exception:
            pass

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Right-click copies log lines to OS clipboard."""
        if event.button == 3:
            self.copy_content()
            event.stop()
            event.prevent_default()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """Right-click copies log lines to OS clipboard."""
        if event.button == 3:
            self.copy_content()
            event.stop()
            event.prevent_default()

    def on_key(self, event: events.Key) -> None:
        """Copy logs on Ctrl+Shift+C or 'y'."""
        key = event.key.lower()
        if key in ("ctrl+shift+c", "ctrl+shift+insert", "y"):
            self.copy_content()
            event.stop()
            event.prevent_default()


def _format_log_entry(entry: LogEntry) -> str:
    """Format a LogEntry into a styled string for display."""
    ts = entry.timestamp.strftime("%H:%M:%S")
    type_colors = {
        "thought": "#a78bfa",
        "tool_call": "#38bdf8",
        "result": "#4ade80",
        "error": "#f87171",
        "info": "$text",
    }
    color = type_colors.get(entry.entry_type, "$text")
    type_badge = entry.entry_type.upper().ljust(9)

    return (
        f"[dim]{ts}[/] "
        f"[bold {color}]{type_badge}[/] "
        f"[{color}]{entry.content}[/]"
    )
