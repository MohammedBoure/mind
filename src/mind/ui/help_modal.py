"""Help modal displaying keyboard shortcuts and usage information."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


_HELP_TEXT = """\
[bold underline #bb9af7]Vim-like Modal Architecture[/]
[bold #e0af68]NORMAL Mode[/]       Vim Command mode (single-key shortcuts, no modifiers needed)
[bold #7aa2f7]PTY Mode[/]          Insert mode (raw keystrokes stream directly to agy.exe stdin)

[bold underline #bb9af7]Mode Switching & Leader Controls[/]
[bold #7aa2f7]i / Enter / a[/]   Enter PTY Insert mode from NORMAL mode
[bold #e0af68]Esc Esc / Ctrl+B[/]  Return to NORMAL mode from PTY (bare Esc passes to agy vim prompt)
[bold #7aa2f7]F12 / Ctrl+][/]     Dedicated leader keys to return to NORMAL mode

[bold underline #bb9af7]Clipboard & Copying[/]
[bold #7aa2f7]y[/]                Yank / copy focused pane selection or terminal buffer (NORMAL mode)
[bold #7aa2f7]Ctrl+Shift+C[/]     Copy selection or terminal buffer to OS clipboard (Any mode)
[bold #7aa2f7]Mouse Select[/]     Highlight text with left click to auto-copy to OS clipboard
[bold #7aa2f7]Right-Click[/]      Copy selection or visible screen lines directly to clipboard

[bold underline #bb9af7]NORMAL Mode Navigation & Tab Controls (Single-Key)[/]
[bold #7aa2f7]1..9[/]             Jump directly to Worker tab N
[bold #7aa2f7]h / l[/]            Switch to previous / next worker tab
[bold #7aa2f7]c[/]                Spawn a new worker agent tab
[bold #7aa2f7]x[/]                Terminate and close active worker tab
[bold #7aa2f7]s[/]                Toggle split layout (Side-by-side / Stacked)
[bold #7aa2f7]Tab[/]              Toggle focus between Primary Agent coordinator & Worker PTY

[bold underline #bb9af7]Inter-Agent & Directive Injection[/]
[bold #7aa2f7]m / Ctrl+M[/]       Open Directive Injection Modal (NORMAL / Any mode)
[bold #7aa2f7]d / Ctrl+D[/]       Open In-App Directive Modal Editor (NORMAL / Any mode)
[bold #7aa2f7]o / Ctrl+O[/]       Open Directive in System Default Editor (NORMAL / Any mode)
[bold #7aa2f7]Ctrl+C[/]           Send immediate interrupt signal (SIGINT) to active Worker

[bold underline #bb9af7]Agent Configuration & Tuning[/]
[bold #7aa2f7]e[/]                Open Agent Config & Flags Modal (NORMAL mode)
[bold #7aa2f7]Ctrl+E[/]           Open Agent Config & Flags Modal (Any mode)

[bold underline #bb9af7]General[/]
[bold #7aa2f7]?[/]                Toggle this help screen
[bold #7aa2f7]q[/]                Quit application and cleanly terminate worker processes
[bold #7aa2f7]Escape[/]           Close modal / return to workspace
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
            yield Static("⌨ [bold #7aa2f7]Mind Vim Modal Shortcuts & Architecture[/]", id="help-title")
            with VerticalScroll(id="help-content"):
                yield Static(_HELP_TEXT)

    def action_dismiss_help(self) -> None:
        """Close the help modal."""
        self.dismiss(None)

    def on_key(self, event) -> None:
        """Close on escape, q, or question mark."""
        if event.key in ("q", "escape", "question_mark"):
            self.dismiss(None)
