"""Main Textual application for the mind TUI.

This is the root App class that orchestrates screen routing,
global keybindings, and the event bridge between UI and backend.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from mind.events import NewSessionRequested, SessionSelected
from mind.state.mock_data import MOCK_SESSIONS
from mind.ui.session_picker import SessionPickerScreen
from mind.ui.workspace import WorkspaceScreen


# Path to the global stylesheet
_CSS_PATH = Path(__file__).parent / "ui" / "styles.tcss"


class MindApp(App):
    """mind — AI Multi-Agent Orchestration TUI.

    Provides a Zellij-inspired terminal multiplexer interface for
    managing multi-agent AI sessions with real-time log streaming,
    inter-agent messaging, and split-pane workspace views.
    """

    TITLE = "mind"
    SUB_TITLE = "AI Multi-Agent Orchestration"
    CSS_PATH = _CSS_PATH

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, initial_session: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_session = initial_session

    def on_mount(self) -> None:
        """Route to the correct screen on startup."""
        if self._initial_session:
            # Direct entry: go straight to workspace
            self._enter_workspace(
                session_name=self._initial_session,
                agent_count=3,
                goal="",
            )
        else:
            # Show session picker
            self.push_screen(SessionPickerScreen())

    def on_session_selected(self, event: SessionSelected) -> None:
        """Handle session selection from the picker."""
        # Look up agent count from mock data
        agent_count = 3
        goal = ""
        for session in MOCK_SESSIONS:
            if session.name == event.session_name:
                agent_count = session.agent_count
                goal = session.goal
                break

        self._enter_workspace(
            session_name=event.session_name,
            agent_count=agent_count,
            goal=goal,
        )

    def on_new_session_requested(self, event: NewSessionRequested) -> None:
        """Handle new session creation request."""
        self._enter_workspace(
            session_name=event.session_name,
            agent_count=event.agent_count,
            goal=event.goal,
        )

    def _enter_workspace(
        self,
        session_name: str,
        agent_count: int,
        goal: str,
    ) -> None:
        """Switch to the workspace screen for the given session."""
        workspace = WorkspaceScreen(
            session_name=session_name,
            agent_count=agent_count,
            goal=goal,
        )
        if len(self.screen_stack) > 1:
            self.switch_screen(workspace)
        else:
            self.push_screen(workspace)



