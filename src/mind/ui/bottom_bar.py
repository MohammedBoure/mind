"""Rich multi-segment status bar widget with clickable interactive action pills.

Dynamically displays available single-key commands for NORMAL mode vs PTY_INTERACT mode.
"""

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
    """Interactive multi-segment status bar inspired by Zellij, Helix, and Vim."""

    DEFAULT_CSS = """
    BottomBar {
        dock: bottom;
        height: 1;
        width: 100%;
        background: #16161e;
        color: #c0caf5;
    }
    """

    mode: reactive[str] = reactive("NORMAL")
    worker_count: reactive[int] = reactive(2)

    def __init__(
        self,
        worker_count: int = 2,
        mode: str = "NORMAL",
        **kwargs,
    ) -> None:
        super().__init__(id="bottom-bar", **kwargs)
        self.worker_count = worker_count
        self.mode = mode

    def compose(self) -> ComposeResult:
        with Horizontal(id="bottom-bar-container"):
            # 1. Left Segment: Modal indicator
            yield Static(self._build_mode_indicator(), id="bottom-mode-pill")

            # 2. Middle Segment: Dynamic Action Badges based on mode
            with Horizontal(id="bottom-actions-container"):
                # Normal Mode Actions
                with Horizontal(id="bottom-normal-actions"):
                    yield ActionPill("i/Enter", "Type in agy", "enter_pty", id="pill-insert")
                    yield ActionPill("1..9", "Jump", "show_help", id="pill-jump")
                    yield ActionPill("h/l", "Prev/Next", "next_worker", id="pill-cycle")
                    yield ActionPill("y", "Copy", "copy_to_clipboard", id="pill-copy-yank")
                    yield ActionPill("m", "Inject", "open_directive_modal", id="pill-inject")
                    yield ActionPill("d/o", "Directive", "open_directive_editor", id="pill-directive")
                    yield ActionPill("e", "Config", "open_agent_config_modal", id="pill-config")
                    yield ActionPill("c", "New Tab", "new_tab", id="pill-new")
                    yield ActionPill("x", "Close Tab", "close_active_tab", id="pill-close")
                    yield ActionPill("s", "Split", "toggle_split", id="pill-split")
                    yield ActionPill("?", "Help", "show_help", id="pill-help")
                    yield ActionPill("q", "Quit", "quit", id="pill-quit")

                # PTY / Insert Mode Actions
                with Horizontal(id="bottom-pty-actions"):
                    yield ActionPill("Esc Esc / Ctrl+B", "Outer Normal", "enter_normal", id="pill-esc")
                    yield ActionPill("Ctrl+Shift+C", "Copy", "copy_to_clipboard", id="pill-copy-pty")
                    yield ActionPill("Ctrl+M", "Inject", "open_directive_modal", id="pill-pty-inject")
                    yield ActionPill("Ctrl+D/O", "Directive", "open_directive_editor", id="pill-pty-directive")
                    yield ActionPill("Ctrl+E", "Config", "open_agent_config_modal", id="pill-pty-config")
                    yield ActionPill("Ctrl+C", "Interrupt", "interrupt_active", id="pill-interrupt")
                    yield ActionPill("?", "Help", "show_help", id="pill-pty-help")

            # 3. Right Segment: PTY Platform / Encoding Status
            backend_info = "ConPTY" if sys.platform == "win32" else "pty"
            yield Static(f"⚡ {backend_info} · UTF-8", id="bottom-status-pill")

    def _build_mode_indicator(self) -> str:
        if self.mode in ("PTY_INTERACT", "PTY"):
            return "[bold #1a1b26 on #7aa2f7] ⌨ PTY INTERACT (Press Esc Esc or Ctrl+B for Outer Normal) [/]"
        return "[bold #1a1b26 on #e0af68] 🔍 NORMAL MODE (Press 'i' to type in agy) [/]"

    def watch_mode(self, value: str) -> None:
        """Toggle visible action pills and update mode indicator when mode changes."""
        is_pty = value in ("PTY_INTERACT", "PTY")
        try:
            self.query_one("#bottom-mode-pill", Static).update(self._build_mode_indicator())
        except Exception:
            pass

        try:
            normal_box = self.query_one("#bottom-normal-actions", Horizontal)
            pty_box = self.query_one("#bottom-pty-actions", Horizontal)
            if is_pty:
                normal_box.styles.display = "none"
                pty_box.styles.display = "block"
            else:
                normal_box.styles.display = "block"
                pty_box.styles.display = "none"
        except Exception:
            pass
