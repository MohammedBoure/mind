"""Workspace screen — the main TUI layout with agent panes and controls."""

from __future__ import annotations

import random
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import TabbedContent, TabPane

from micro.events import AgentLogAppend, InterruptReceived
from micro.state.mock_data import (
    get_mock_agents,
    get_mock_log_stream,
    get_random_interrupt_message,
)
from micro.state.models import AgentInfo, AgentStatus, LogEntry
from micro.ui.agent_pane import AgentLogPane
from micro.ui.bottom_bar import BottomBar
from micro.ui.header_bar import HeaderBar
from micro.ui.interrupt_banner import InterruptBanner


class WorkspaceScreen(Screen):
    """Main workspace screen with split-pane agent views.

    Layout:
    ┌─────────────────────────────────────────────────┐
    │ HeaderBar: Session name | Status | Agent tabs   │
    ├─────────────────────────────────────────────────┤
    │ InterruptBanner (hidden until triggered)        │
    ├────────────────────┬────────────────────────────┤
    │ Primary Agent Pane │ Worker Panes (tabbed)      │
    │ (left / main)      │ (right / secondary)        │
    ├────────────────────┴────────────────────────────┤
    │ BottomBar: Keybind hints                        │
    └─────────────────────────────────────────────────┘
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("question_mark", "show_help", "Help"),
        ("m", "mock_interrupt", "Mock Interrupt"),
        ("n", "new_tab", "New Tab"),
        ("s", "toggle_split", "Toggle Split"),
        ("escape", "go_back", "Back"),
    ]

    def __init__(
        self,
        session_name: str = "default",
        agent_count: int = 3,
        goal: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._session_name = session_name
        self._agent_count = max(agent_count, 1)
        self._goal = goal
        self._agents: list[AgentInfo] = []
        self._panes: dict[int, AgentLogPane] = {}
        self._is_horizontal = True  # True = side-by-side, False = stacked
        self._stream_timer = None

    def compose(self) -> ComposeResult:
        # Generate mock agents
        self._agents = get_mock_agents(self._agent_count)

        # Header
        yield HeaderBar(
            session_name=self._session_name,
            agents=self._agents,
        )

        # Interrupt banner (hidden by default)
        yield InterruptBanner()

        # Workspace: Primary pane + Worker panes
        primary = self._agents[0]
        primary_logs = get_mock_log_stream(primary.id)
        primary_pane = AgentLogPane(
            agent=primary,
            logs=primary_logs,
            pane_id="primary-pane",
        )
        self._panes[primary.id] = primary_pane

        with Horizontal(id="workspace-container"):
            yield primary_pane

            # Worker panes inside a tabbed container
            if len(self._agents) > 1:
                with Vertical(id="workers-pane"):
                    with TabbedContent(id="worker-tabs"):
                        for agent in self._agents[1:]:
                            worker_logs = get_mock_log_stream(agent.id)
                            pane = AgentLogPane(
                                agent=agent,
                                logs=worker_logs,
                                pane_id=f"worker-pane-{agent.id}",
                            )
                            self._panes[agent.id] = pane
                            with TabPane(
                                f"{agent.name}",
                                id=f"worker-tab-{agent.id}",
                            ):
                                yield pane

        yield BottomBar()

    def on_mount(self) -> None:
        """Start the simulated log stream after mounting."""
        self._stream_timer = self.set_interval(2.5, self._emit_mock_log)

    def _emit_mock_log(self) -> None:
        """Periodically emit a mock log entry to a random agent."""
        if not self._agents:
            return

        agent = random.choice(self._agents)
        entry_types = ["thought", "tool_call", "result", "info"]
        mock_lines = [
            ("thought", "Evaluating next step in the workflow..."),
            ("tool_call", "→ analyze_dependencies('src/core/')"),
            ("result", "✓ Dependency graph resolved. 14 modules mapped."),
            ("info", "Checkpoint saved. Progress: 67%"),
            ("thought", "Considering alternative approach for module isolation..."),
            ("tool_call", "→ run_tests('tests/unit/')"),
            ("result", "✓ 23/23 tests passed."),
            ("info", "Syncing state with peer agents..."),
            ("thought", "Reviewing code quality metrics..."),
            ("tool_call", "→ lint_check('src/')"),
            ("result", "✓ No issues found."),
            ("error", "⚠ Timeout waiting for Worker-3 response."),
        ]

        entry_type, content = random.choice(mock_lines)
        entry = LogEntry(
            timestamp=datetime.now(),
            source=f"Agent-{agent.id}",
            content=content,
            entry_type=entry_type,
        )

        # Append directly to the pane
        pane = self._panes.get(agent.id)
        if pane:
            pane.append_log(entry)

    # ── Actions ───────────────────────────────────────────────────

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()

    def action_show_help(self) -> None:
        """Show the help modal."""
        from micro.ui.help_modal import HelpModal

        self.app.push_screen(HelpModal())

    def action_mock_interrupt(self) -> None:
        """Trigger a mock inter-agent interrupt message."""
        message = get_random_interrupt_message()
        banner = self.query_one(InterruptBanner)
        banner.show_interrupt(message)

    def action_new_tab(self) -> None:
        """Placeholder for adding a new agent tab."""
        self.notify("New agent tab (placeholder — wire to backend)", severity="information")

    def action_toggle_split(self) -> None:
        """Toggle between horizontal and vertical split layout."""
        container = self.query_one("#workspace-container")
        self._is_horizontal = not self._is_horizontal
        if self._is_horizontal:
            container.styles.layout = "horizontal"
            self.notify("Layout: side-by-side")
        else:
            container.styles.layout = "vertical"
            self.notify("Layout: stacked")

    def action_go_back(self) -> None:
        """Go back to session picker."""
        if self._stream_timer:
            self._stream_timer.stop()
        # Pop this screen to return to the picker
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()
