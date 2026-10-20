"""Streamlined Zellij-inspired header bar widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class HeaderBar(Widget):
    """Clean top bar displaying branding, session name, agent telemetry, and MCP status."""

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
            yield Static("🧠 [bold #7aa2f7]mind[/]", id="brand-pill")

            # Active session pill
            yield Static(f"📂 [dim]{self.session_name}[/]", id="session-pill")

            # Center spacer
            yield Static("", id="header-spacer")

            # Active worker telemetry
            yield Static(f"⚡ [bold #e0af68]{self.worker_count}[/] [dim]active workers[/]", id="worker-count-pill")

            # MCP Health status indicator
            yield Static(f"⚡ [bold #9ece6a]MCP[/] [dim]:{self.mcp_port}[/]", id="mcp-indicator")

    def watch_session_name(self, value: str) -> None:
        try:
            self.query_one("#session-pill", Static).update(f"📂 [dim]{value}[/]")
        except Exception:
            pass

    def watch_worker_count(self, value: int) -> None:
        try:
            self.query_one("#worker-count-pill", Static).update(f"⚡ [bold #e0af68]{value}[/] [dim]active workers[/]")
        except Exception:
            pass
