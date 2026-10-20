"""Interrupt banner widget for inter-agent message alerts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from mind.state.models import InterAgentMessage, MessagePriority


# Priority display configuration
_PRIORITY_STYLES: dict[MessagePriority, tuple[str, str]] = {
    MessagePriority.CRITICAL: ("🔴 CRITICAL", "interrupt-priority-critical"),
    MessagePriority.HIGH: ("🟠 HIGH", "interrupt-priority-high"),
    MessagePriority.NORMAL: ("🟢 NORMAL", "interrupt-priority-normal"),
    MessagePriority.LOW: ("⚪ LOW", "interrupt-priority-low"),
}


class InterruptBanner(Widget):
    """Visual alert component for inter-agent message interrupts.

    Highlights incoming messages with sender profile, priority level,
    and injected directive. Simulates the pause-and-resume protocol.
    """

    is_visible: reactive[bool] = reactive(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(id="interrupt-banner", **kwargs)
        self._current_message: InterAgentMessage | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="interrupt-content")

    def show_interrupt(self, message: InterAgentMessage) -> None:
        """Display an interrupt message with full visual treatment."""
        self._current_message = message
        priority_label, priority_class = _PRIORITY_STYLES.get(
            message.priority, ("● UNKNOWN", "interrupt-priority-normal")
        )

        content = (
            f"[bold yellow]⚡ INTERRUPT[/]  │  "
            f"[bold cyan]{message.sender}[/] → {message.receiver}  │  "
            f"[{priority_class}]{priority_label}[/]\n"
            f"   {message.directive}"
        )

        try:
            content_widget = self.query_one("#interrupt-content", Static)
            content_widget.update(content)
        except Exception:
            pass

        self.is_visible = True
        self.add_class("visible")

        # Auto-dismiss after 6 seconds
        self.set_timer(6.0, self.dismiss_interrupt)

    def dismiss_interrupt(self) -> None:
        """Hide the interrupt banner."""
        self.is_visible = False
        self.remove_class("visible")
