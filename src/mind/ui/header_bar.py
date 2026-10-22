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
    quota_text: reactive[str] = reactive("[dim]Quota:[/] [bold #9ece6a][██████████] 100%[/]")

    def __init__(
        self,
        session_name: str = "unnamed",
        worker_count: int = 2,
        mode: str = "NORMAL",
        quota_text: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.session_name = session_name
        self.worker_count = worker_count
        self.mode = mode
        if quota_text:
            self.quota_text = quota_text

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            # Brand logo pill
            yield Static("[bold #7aa2f7]mind[/]", id="brand-pill")

            # Active session pill
            yield Static(f"[dim]{self.session_name}[/]", id="session-pill")

            # Center spacer
            yield Static("", id="header-spacer")

            # Active worker telemetry
            yield Static(f"[bold #e0af68]{self.worker_count}[/] [dim]active workers[/]", id="worker-count-pill")

            # Live Quota Badge
            yield Static(self.quota_text, id="quota-pill")

            # MCP Health status indicator
            yield Static(f"[bold #9ece6a]MCP[/] [dim]:{self.mcp_port}[/]", id="mcp-indicator")

    def on_mount(self) -> None:
        """Initialize live quota telemetry and register recurring check."""
        self._refresh_quota()
        self.set_interval(30.0, self._refresh_quota)

    def _refresh_quota(self) -> None:
        """Query UsageMonitor for live account quota consumption."""
        try:
            from mind.core.usage_monitor import UsageMonitor
            monitor = UsageMonitor()
            usage = monitor.get_slot_usage("agy1")
            bar = usage.hourly_bar or usage.colored_progress_bar
            if bar:
                self.quota_text = f"[dim]Quota:[/] {bar}"
            else:
                self.update_quota(usage.hourly_remaining_percent, usage.status.value)
        except Exception:
            pass

    def update_quota(
        self,
        remaining_percent: float = 100.0,
        status: str = "normal",
        text: str | None = None,
    ) -> None:
        """Update the Live Quota Badge with current percentage and status."""
        if text is not None:
            self.quota_text = text
            return

        try:
            from mind.core.usage_monitor import render_colored_bar, QuotaStatus
            q_status = QuotaStatus(status) if status in ("normal", "warning", "throttled") else QuotaStatus.NORMAL
            bar = render_colored_bar(remaining_percent, q_status, width=10)
            self.quota_text = f"[dim]Quota:[/] {bar}"
        except Exception:
            self.quota_text = f"[dim]Quota:[/] [bold #9ece6a][██████████] {int(remaining_percent)}%[/]"

    def watch_session_name(self, value: str) -> None:
        try:
            self.query_one("#session-pill", Static).update(f"[dim]{value}[/]")
        except Exception:
            pass

    def watch_worker_count(self, value: int) -> None:
        try:
            self.query_one("#worker-count-pill", Static).update(f"[bold #e0af68]{value}[/] [dim]active workers[/]")
        except Exception:
            pass

    def watch_quota_text(self, value: str) -> None:
        try:
            self.query_one("#quota-pill", Static).update(value)
        except Exception:
            pass
