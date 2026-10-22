"""Session Picker screen — the landing screen when running `mind`.

Provides keyboard-first session management, disk persistence, and live
activity statistics inspection (agent counts, active state, steps, and last activity).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from mind.core.session_storage import (
    SessionRecord,
    delete_session,
    load_all_sessions,
)
from mind.events import SessionSelected


class SessionPickerScreen(Screen):
    """Screen showing existing sessions and allowing selection, creation, and deletion."""

    BINDINGS = [
        ("n", "new_session", "New Session"),
        ("d", "delete_session", "Delete Session"),
        ("x", "delete_session", "Delete Session"),
        ("r", "refresh_sessions", "Refresh"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "select_current", "Select"),
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sessions: list[SessionRecord] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="session-picker-container"):
            with Vertical(id="picker-panel"):
                yield Static(
                    "🧠  [bold #7aa2f7]mind[/bold #7aa2f7]",
                    id="picker-title",
                )
                yield Static(
                    "[dim]AI Multi-Agent Orchestration Multiplexer[/dim]",
                    id="picker-subtitle",
                )

                # Build session options list
                option_list = OptionList(id="session-list")
                yield option_list

                yield Static(
                    "[bold #7aa2f7]↑↓/jk[/] Navigate  ·  [bold #7aa2f7]Enter[/] Open  ·  [bold #9ece6a]n[/] New  ·  [bold #f7768e]d[/] Delete  ·  [bold #e0af68]r[/] Refresh  ·  [bold #bb9af7]q[/] Quit",
                    id="picker-footer",
                )

    def on_mount(self) -> None:
        """Populate the session list on mount and focus the list."""
        self.refresh_sessions()
        try:
            self.query_one("#session-list", OptionList).focus()
        except Exception:
            pass

    def refresh_sessions(self) -> None:
        """Reload sessions from persistent storage and rebuild option list."""
        self.sessions = load_all_sessions()
        option_list = self.query_one("#session-list", OptionList)
        option_list.clear_options()

        if not self.sessions:
            option_list.add_option(
                Option("[dim italic]No active sessions found. Press 'n' to create a new session.[/dim italic]", id=None)
            )
            return

        for session in self.sessions:
            created_ago = _relative_time(session.created_at)
            active_ago = _relative_time(session.last_activity)
            status_badge = "[bold #9ece6a]● Active[/]" if session.active else "[dim #565f89]○ Archived[/]"

            stats_info = f"⚡ {session.total_steps} steps · {session.total_interactions} tasks"
            timing_info = f"Created: {created_ago} · Active: {active_ago}"

            label = (
                f"[bold #7aa2f7]{session.name:<18}[/] "
                f"[dim #7dcfff]({session.agent_count} agents)[/]  "
                f"{status_badge}  "
                f"[dim #e0af68]{stats_info}[/]  "
                f"[dim]({timing_info})[/]\n"
                f"   [italic #a9b1d6]{session.goal or 'General workspace'}[/]"
            )
            option_list.add_option(Option(label, id=session.name))

        if option_list.option_count > 0:
            option_list.highlighted = 0

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle session selection when chosen via Enter or click."""
        if event.option.id is not None:
            self.post_message(SessionSelected(session_name=str(event.option.id)))

    def on_key(self, event: events.Key) -> None:
        """Keyboard event interceptor for smooth Vim j/k navigation and action triggers."""
        key = event.key
        if key in ("j", "down"):
            self.action_cursor_down()
            event.stop()
            event.prevent_default()
        elif key in ("k", "up"):
            self.action_cursor_up()
            event.stop()
            event.prevent_default()
        elif key in ("d", "x"):
            self.action_delete_session()
            event.stop()
            event.prevent_default()
        elif key == "r":
            self.action_refresh_sessions()
            event.stop()
            event.prevent_default()
        elif key == "n":
            self.action_new_session()
            event.stop()
            event.prevent_default()

    def action_cursor_down(self) -> None:
        """Move cursor down in session list."""
        try:
            opt = self.query_one("#session-list", OptionList)
            if opt.option_count > 0:
                current = opt.highlighted if opt.highlighted is not None else -1
                if current < opt.option_count - 1:
                    opt.highlighted = current + 1
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        """Move cursor up in session list."""
        try:
            opt = self.query_one("#session-list", OptionList)
            if opt.option_count > 0:
                current = opt.highlighted if opt.highlighted is not None else 1
                if current > 0:
                    opt.highlighted = current - 1
        except Exception:
            pass

    def action_select_current(self) -> None:
        """Select highlighted session."""
        try:
            opt = self.query_one("#session-list", OptionList)
            if opt.highlighted is not None and opt.highlighted < len(self.sessions):
                selected_sess = self.sessions[opt.highlighted]
                self.post_message(SessionSelected(session_name=selected_sess.name))
        except Exception:
            pass

    def action_delete_session(self) -> None:
        """Delete highlighted session from disk."""
        try:
            opt = self.query_one("#session-list", OptionList)
            if opt.highlighted is None or opt.highlighted >= len(self.sessions):
                return

            target = self.sessions[opt.highlighted]
            deleted = delete_session(target.name)
            if deleted:
                self.refresh_sessions()
                try:
                    self.notify(f"🗑 Session '{target.name}' deleted.", severity="warning", timeout=2.0)
                except Exception:
                    pass
        except Exception as e:
            try:
                self.notify(f"Could not delete session: {e}", severity="error")
            except Exception:
                pass

    def action_refresh_sessions(self) -> None:
        """Manually refresh session list from disk."""
        self.refresh_sessions()
        try:
            self.notify("↻ Sessions refreshed from disk", severity="information", timeout=1.5)
        except Exception:
            pass

    def action_new_session(self) -> None:
        """Open the new session modal."""
        from mind.ui.new_session_modal import NewSessionModal

        self.app.push_screen(NewSessionModal(), callback=lambda _: self.refresh_sessions())

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()


def _relative_time(dt: datetime) -> str:
    """Return a human-friendly relative time string."""
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 0 or seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    return f"{days}d ago"
