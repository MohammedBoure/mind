"""New Session modal dialog for creating a new agent session."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from mind.events import NewSessionRequested


class NewSessionModal(ModalScreen[None]):
    """Modal dialog for configuring and creating a new session."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="new-session-dialog"):
            yield Static("✨  [bold]Create New Session[/bold]", id="modal-title")

            with Vertical(classes="modal-field"):
                yield Label("Session Name:", classes="modal-label")
                yield Input(
                    placeholder="e.g., refactor-auth",
                    id="session-name-input",
                )

            with Vertical(classes="modal-field"):
                yield Label("Number of Agents:", classes="modal-label")
                yield Input(
                    placeholder="3",
                    id="agent-count-input",
                    value="3",
                )

            with Vertical(classes="modal-field"):
                yield Label("Session Goal:", classes="modal-label")
                yield Input(
                    placeholder="Describe the session objective...",
                    id="session-goal-input",
                )

            with Horizontal(id="modal-buttons"):
                yield Button("Create", variant="success", id="btn-create")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        """Focus the session name input on mount."""
        self.query_one("#session-name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-create":
            self._create_session()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Allow Enter key to submit from any input field."""
        self._create_session()

    def _create_session(self) -> None:
        """Validate inputs and post a NewSessionRequested message."""
        name_input = self.query_one("#session-name-input", Input)
        count_input = self.query_one("#agent-count-input", Input)
        goal_input = self.query_one("#session-goal-input", Input)

        session_name = name_input.value.strip()
        if not session_name:
            name_input.focus()
            self.notify("Session name is required.", severity="error")
            return

        try:
            agent_count = int(count_input.value.strip() or "3")
            if agent_count < 1:
                raise ValueError
        except ValueError:
            count_input.focus()
            self.notify("Agent count must be a positive integer.", severity="error")
            return

        goal = goal_input.value.strip()

        self.post_message(
            NewSessionRequested(
                session_name=session_name,
                agent_count=agent_count,
                goal=goal,
            )
        )
        self.dismiss(None)

    def action_cancel(self) -> None:
        """Dismiss the modal."""
        self.dismiss(None)
