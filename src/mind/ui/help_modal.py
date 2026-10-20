"""Help modal displaying keyboard shortcuts and usage information."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


_HELP_TEXT = """\
[bold underline]Navigation[/bold underline]
[bold cyan]Alt+1..9[/]        Switch to agent tab N
[bold cyan]Tab[/]             Cycle focus between panes
[bold cyan]Shift+Tab[/]       Cycle focus reverse

[bold underline]Actions[/bold underline]
[bold cyan]m[/]               Trigger mock inter-agent interrupt
[bold cyan]n[/]               Open new tab / session
[bold cyan]s[/]               Toggle split view orientation

[bold underline]Scrolling[/bold underline]
[bold cyan]↑ / ↓[/]           Scroll active log pane
[bold cyan]Home / End[/]      Jump to top / bottom of log

[bold underline]General[/bold underline]
[bold cyan]?[/]               Toggle this help screen
[bold cyan]q[/]               Quit the application
[bold cyan]Escape[/]          Close modal / go back
"""


class HelpModal(ModalScreen[None]):
    """Modal overlay showing all keyboard shortcuts."""

    BINDINGS = [
        ("escape", "dismiss_help", "Close"),
        ("question_mark", "dismiss_help", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(
                "⌨  [bold]Keyboard Shortcuts[/bold]", id="help-title"
            )
            with VerticalScroll(id="help-content"):
                yield Static(_HELP_TEXT)

    def action_dismiss_help(self) -> None:
        """Close the help modal."""
        self.dismiss(None)

    def on_key(self, event) -> None:
        """Close on any unbound key press as well."""
        if event.key in ("q", "escape", "question_mark"):
            self.dismiss(None)
