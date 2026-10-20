"""Session Picker screen — the landing screen when running `micro`."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, OptionList, Static
from textual.widgets.option_list import Option

from micro.events import SessionSelected
from micro.state.mock_data import MOCK_SESSIONS


class SessionPickerScreen(Screen):
    """Screen showing existing sessions and allowing selection or creation."""

    BINDINGS = [
        ("n", "new_session", "New Session"),
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="session-picker-container"):
            with Vertical(id="picker-panel"):
                yield Static(
                    "🧠  [bold]mind · micro[/bold]",
                    id="picker-title",
                )
                yield Static(
                    "AI Multi-Agent Orchestration TUI",
                    id="picker-subtitle",
                )

                # Build session options
                option_list = OptionList(id="session-list")
                yield option_list

                yield Static(
                    "[dim]↑/↓ Navigate  ·  Enter Select  ·  n New  ·  q Quit[/dim]",
                    id="picker-footer",
                )

    def on_mount(self) -> None:
        """Populate the session list on mount."""
        option_list = self.query_one("#session-list", OptionList)
        for session in MOCK_SESSIONS:
            ago = _relative_time(session.created_at)
            label = (
                f"[bold]{session.name}[/bold]  "
                f"[dim]({session.agent_count} agents · {ago})[/dim]  "
                f"[italic dim]{session.goal}[/italic dim]"
            )
            option_list.add_option(Option(label, id=session.name))

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle session selection."""
        if event.option.id is not None:
            self.post_message(SessionSelected(session_name=str(event.option.id)))

    def action_new_session(self) -> None:
        """Open the new session modal."""
        from micro.ui.new_session_modal import NewSessionModal

        self.app.push_screen(NewSessionModal())

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()


def _relative_time(dt: "datetime") -> str:  # noqa: F821
    """Return a human-friendly relative time string."""
    from datetime import datetime

    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    return f"{days}d ago"
