"""Rich multi-segment status bar widget with clickable interactive action pills."""

from __future__ import annotations

import sys
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class ActionPill(Static):
    """Clickable shortcut badge in the bottom status bar."""

    def __init__(self, key: str, label: str, action: str, **kwargs) -> None:
        self.action_name = action
        text = f"[bold #7aa2f7]{key}[/] [dim]{label}[/]"
        super().__init__(text, classes="action-pill", **kwargs)

    def on_click(self) -> None:
        """Execute corresponding action on click."""
        if self.action_name:
            self.run_action(self.action_name)


class BottomBar(Widget):
    """Interactive multi-segment status bar inspired by Zellij and Helix."""

    mode: reactive[str] = reactive("NORMAL")
    worker_count: reactive[int] = reactive(2)

    def __init__(
        self,
        worker_count: int = 2,
        **kwargs,
    ) -> None:
        super().__init__(id="bottom-bar", **kwargs)
        self.worker_count = worker_count

    def compose(self) -> ComposeResult:
        with Horizontal(id="bottom-bar-container"):
            # 1. Left Segment: Mode indicator
            yield Static(self._build_mode_indicator(), id="bottom-mode-pill")

            # 2. Middle Segment: Clickable Action Badges
            with Horizontal(id="bottom-actions-container"):
                yield ActionPill("Alt+1..N", "Switch", "next_worker", id="pill-switch")
                yield ActionPill("Tab", "Focus", "focus_next", id="pill-focus")
                yield ActionPill("Ctrl+M", "Inject", "open_directive_modal", id="pill-inject")
                yield ActionPill("s", "Split", "toggle_split", id="pill-split")
                yield ActionPill("Ctrl+C", "Interrupt", "interrupt_active", id="pill-interrupt")
                yield ActionPill("?", "Help", "show_help", id="pill-help")
                yield ActionPill("q", "Quit", "quit", id="pill-quit")

            # 3. Right Segment: PTY Encoding Status
            backend_info = "ConPTY" if sys.platform == "win32" else "pty"
            yield Static(f"⚡ {backend_info} · UTF-8", id="bottom-status-pill")

    def _build_mode_indicator(self) -> str:
        if self.mode == "PTY INTERACT":
            return "[bold #1a1b26 on #bb9af7] PTY INPUT [/]"
        return "[bold #1a1b26 on #7aa2f7] NORMAL [/]"

    def watch_mode(self, value: str) -> None:
        try:
            self.query_one("#bottom-mode-pill", Static).update(self._build_mode_indicator())
        except Exception:
            pass
