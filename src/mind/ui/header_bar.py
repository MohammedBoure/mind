"""Streamlined Zellij-inspired header bar widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class HeaderBar(Widget):
    """Zellij-inspired top bar displaying branding, session, mode, and MCP health."""

    DEFAULT_CSS = """
    HeaderBar {
        dock: top;
        height: 1;
        width: 100%;
        background: #16161e;
        color: #c0caf5;
    }
    """

    session_name: reactive[str] = reactive("unnamed")
    mode: reactive[str] = reactive("NORMAL")
    mcp_port: reactive[int] = reactive(8765)
    worker_count: reactive[int] = reactive(2)

    def __init__(
        self,
        session_name: str = "unnamed",
        worker_count: int = 2,
        mode: str = "NORMAL",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.session_name = session_name
        self.worker_count = worker_count
        self.mode = mode

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            # Brand logo pill
            yield Static("🧠 mind", id="brand-pill")

            # Active session pill
            yield Static(f"📂 {self.session_name}", id="session-pill")

            # Interactive mode badge (Vim modal state)
            yield Static(self._build_mode_badge(), id="mode-badge")

            # Center spacer
            yield Static("", id="header-spacer")

            # MCP Health status indicator
            yield Static(f"● MCP {self.mcp_port}", id="mcp-indicator")

            # Active worker count
            yield Static(f"⚡ {self.worker_count} Workers", id="worker-count-pill")

    def _build_mode_badge(self) -> str:
        """Construct the mode indicator badge."""
        if self.mode in ("PTY_INTERACT", "PTY"):
            return "[bold #1a1b26 on #7aa2f7] ⌨ PTY INTERACT (Press Esc for Normal) [/]"
        return "[bold #1a1b26 on #e0af68] 🔍 NORMAL MODE (Press 'i' to type in agy) [/]"

    def watch_session_name(self, value: str) -> None:
        try:
            self.query_one("#session-pill", Static).update(f"📂 {value}")
        except Exception:
            pass

    def watch_mode(self, value: str) -> None:
        try:
            self.query_one("#mode-badge", Static).update(self._build_mode_badge())
        except Exception:
            pass

    def watch_worker_count(self, value: int) -> None:
        try:
            self.query_one("#worker-count-pill", Static).update(f"⚡ {value} Workers")
        except Exception:
            pass
