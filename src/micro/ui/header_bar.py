"""Header bar widget with session info and agent tabs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane

from micro.state.models import AgentInfo, AgentStatus


# Status emoji mapping
_STATUS_ICONS: dict[AgentStatus, str] = {
    AgentStatus.IDLE: "⏸",
    AgentStatus.THINKING: "🧠",
    AgentStatus.EXECUTING: "⚡",
    AgentStatus.WAITING: "⏳",
    AgentStatus.ERROR: "❌",
}


class HeaderBar(Widget):
    """Top bar displaying session name, status, and agent tabs."""

    session_name: reactive[str] = reactive("unnamed")
    is_active: reactive[bool] = reactive(True)

    def __init__(
        self,
        session_name: str = "unnamed",
        agents: list[AgentInfo] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.session_name = session_name
        self._agents = agents or []

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Static(
                f"🧠 {self.session_name}",
                id="session-badge",
            )
            yield Static("● Active", id="status-indicator")

            # Agent tabs
            with TabbedContent(id="agent-tabs"):
                for agent in self._agents:
                    icon = _STATUS_ICONS.get(agent.status, "●")
                    tab_label = f"{icon} {agent.id}: {agent.name}"
                    with TabPane(tab_label, id=f"agent-tab-{agent.id}"):
                        yield Static("")  # Placeholder content inside tab

    def watch_session_name(self, value: str) -> None:
        """Update the session badge when name changes."""
        try:
            badge = self.query_one("#session-badge", Static)
            badge.update(f"🧠 {value}")
        except Exception:
            pass

    def watch_is_active(self, value: bool) -> None:
        """Update the status indicator."""
        try:
            indicator = self.query_one("#status-indicator", Static)
            if value:
                indicator.update("● Active")
                indicator.styles.color = "green"
            else:
                indicator.update("○ Paused")
                indicator.styles.color = "yellow"
        except Exception:
            pass
