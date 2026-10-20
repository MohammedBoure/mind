"""Help modal displaying keyboard shortcuts and usage information."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


_HELP_TEXT = """\
[bold underline #bb9af7]Navigation & Focus[/]
[bold #7aa2f7]Alt+1..9[/]        Switch directly to Worker tab N
[bold #7aa2f7]Tab[/]             Toggle focus between Primary Agent & Worker PTY
[bold #7aa2f7]Shift+Tab[/]       Cycle widget focus in reverse

[bold underline #bb9af7]Inter-Agent & Terminal Actions[/]
[bold #7aa2f7]Ctrl+M[/]          Open Directive Injection Modal (Targeted Inter-Agent Interrupt)
[bold #7aa2f7]Ctrl+C[/]          Send immediate interrupt signal (SIGINT) to active Worker
[bold #7aa2f7]m[/]               Simulate quick random interrupt test
[bold #7aa2f7]n[/]               Spawn a new live Worker PTY tab
[bold #7aa2f7]s[/]               Toggle split layout (Side-by-side / Stacked)

[bold underline #bb9af7]Scrolling & Inspection[/]
[bold #7aa2f7]↑ / ↓[/]           Scroll terminal screen buffer or coordinator log
[bold #7aa2f7]PgUp / PgDn[/]     Page scroll terminal buffer
[bold #7aa2f7]Home / End[/]      Jump to top or bottom of output

[bold underline #bb9af7]System & App[/]
[bold #7aa2f7]?[/]               Toggle this help screen
[bold #7aa2f7]Escape[/]          Close modal / return to workspace
[bold #7aa2f7]q[/]               Quit application and terminate background processes
"""


class HelpModal(ModalScreen[None]):
    """Modal overlay showing all keyboard shortcuts with Tokyo Night theme."""

    BINDINGS = [
        ("escape", "dismiss_help", "Close"),
        ("question_mark", "dismiss_help", "Close"),
        ("q", "dismiss_help", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("⌨ [bold #7aa2f7]Mind Keyboard Shortcuts & Architecture[/]", id="help-title")
            with VerticalScroll(id="help-content"):
                yield Static(_HELP_TEXT)

    def action_dismiss_help(self) -> None:
        """Close the help modal."""
        self.dismiss(None)

    def on_key(self, event) -> None:
        """Close on escape, q, or question mark."""
        if event.key in ("q", "escape", "question_mark"):
            self.dismiss(None)
