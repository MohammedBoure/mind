"""Interactive Terminal Tab widget for Textual TUI.

Hosts a real PTY session running agy (or shell), renders the virtual screen
buffer with full ANSI styles, captures user keystrokes for direct interactive
control, and displays visual toast badges upon MCP directive injections.
Implements Vim-like modal input (NORMAL vs PTY_INTERACT).
"""

from __future__ import annotations

import sys
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from mind.core.terminal_manager import WorkerProcessState, WorkerSession


# ANSI escape sequences for key combinations
_SPECIAL_KEYS: dict[str, str] = {
    "enter": "\r\n" if sys.platform == "win32" else "\r",
    "backspace": "\x08" if sys.platform == "win32" else "\x7f",
    "tab": "\t",
    "escape": "\x1b",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "delete": "\x1b[3~",
    "ctrl+c": "\x03",
    "ctrl+d": "\x04",
    "ctrl+z": "\x1a",
    "ctrl+l": "\x0c",
    "ctrl+a": "\x01",
    "ctrl+e": "\x05",
    "ctrl+u": "\x15",
    "ctrl+k": "\x0b",
    "ctrl+w": "\x17",
}


class TerminalScreenWidget(Widget):
    """The interactive terminal screen pane within a worker tab.

    Can be focused to capture raw keystrokes in PTY_INTERACT mode, or allows
    single-key navigation commands to bubble to WorkspaceScreen in NORMAL mode.
    Renders the live ANSI screen buffer or an informative banner when starting up.
    """

    can_focus = True
    mode: reactive[str] = reactive("NORMAL")

    DEFAULT_CSS = """
    TerminalScreenWidget {
        height: 1fr;
        width: 100%;
        min-height: 15;
        background: #0f141c;
        border: round #3b4261;
        padding: 0 1;
        overflow-y: hidden;
        overflow-x: hidden;
    }

    TerminalScreenWidget.mode-pty:focus {
        border: round #7aa2f7;
    }

    TerminalScreenWidget.mode-normal:focus {
        border: round #e0af68;
    }
    """

    class TerminalFocusChanged(Message):
        """Emitted when terminal focus changes to update focus indicators."""
        def __init__(self, is_focused: bool) -> None:
            super().__init__()
            self.is_focused = is_focused

    class ModeChangeRequested(Message):
        """Emitted when user requests switching between NORMAL and PTY modes."""
        def __init__(self, target_mode: str) -> None:
            super().__init__()
            self.target_mode = target_mode

    class OpenDirectiveRequested(Message):
        """Emitted when user triggers directive modal (e.g. via Ctrl+M) from PTY mode."""
        pass

    class OpenConfigRequested(Message):
        """Emitted when user triggers agent config modal (e.g. via Ctrl+E) from PTY mode."""
        pass

    def __init__(self, worker_session: WorkerSession, mode: str = "NORMAL", **kwargs) -> None:
        super().__init__(**kwargs)
        self.worker_session = worker_session
        self.mode = mode
        self._last_rendered_version = -1
        self.add_class("terminal-screen")
        self._sync_mode_classes()

    def _sync_mode_classes(self) -> None:
        """Update CSS classes corresponding to the current modal state."""
        if self.is_pty_mode:
            self.remove_class("mode-normal")
            self.add_class("mode-pty")
        else:
            self.remove_class("mode-pty")
            self.add_class("mode-normal")

    def watch_mode(self, new_mode: str) -> None:
        """React to external mode changes (e.g. from WorkspaceScreen)."""
        self._sync_mode_classes()
        self.refresh()

    @property
    def is_pty_mode(self) -> bool:
        """Return True if currently in direct PTY input (Insert) mode."""
        return self.mode in ("PTY_INTERACT", "PTY")

    def render(self) -> Text:
        """Render virtual screen buffer or placeholder banner if still initializing."""
        visible_lines = self.worker_session.buffer.get_visible_lines()
        has_content = any(line.strip() for line in visible_lines)

        if has_content:
            return self.worker_session.buffer.get_rich_text(show_cursor=self.has_focus)

        return self._render_placeholder_banner()

    def _render_placeholder_banner(self) -> Text:
        """Render an elegant Tokyo Night placeholder banner while buffer initializes."""
        t = Text()
        s = self.worker_session
        pid_str = f"PID: {s.pid}" if s.pid else "Spawning..."
        mode_str = "ConPTY / UTF-8" if sys.platform == "win32" else "Unix PTY / UTF-8"

        is_coordinator = (
            self.worker_session.role == "coordinator"
            or str(self.worker_session.worker_id) == "coordinator"
        )
        tab_title = "Primary Coordinator" if is_coordinator else "Interactive Worker Terminal"

        t.append("\n")
        t.append("   ╭────────────────────────────────────────────────────────────────────────╮\n", style="#3b4261")
        t.append("   │  ", style="#3b4261")
        t.append("🧠  mind ", style="bold #7aa2f7")
        t.append("· ", style="#565f89")
        t.append(f"{tab_title} ", style="bold #bb9af7")
        t.append(f"({s.name})", style="bold #7dcfff")
        fill_spaces = max(1, 44 - len(s.name) - (len(tab_title) - 27))
        t.append(" " * fill_spaces)
        t.append("│\n", style="#3b4261")
        t.append("   ├────────────────────────────────────────────────────────────────────────┤\n", style="#3b4261")
        t.append("   │  ", style="#3b4261")
        t.append("Status: ", style="#7982a9")
        t.append("● RUNNING ", style="bold #9ece6a")
        t.append(f"│  {pid_str:<14} │  Model: {s.model:<10} │  {mode_str}\n", style="#7982a9")
        t.append("   │  ", style="#3b4261")
        t.append("Task:   ", style="#7982a9")
        t.append(f"{s.task[:58]:<58}", style="italic #c0caf5")
        t.append("│\n", style="#3b4261")
        t.append("   ├────────────────────────────────────────────────────────────────────────┤\n", style="#3b4261")

        if self.is_pty_mode:
            focus_hint = "[ ⌨ PTY INTERACT (Press Esc for Normal) ]"
            focus_style = "bold #7aa2f7"
        else:
            focus_hint = "[ 🔍 NORMAL MODE (Press 'i' to type in agy) ]"
            focus_style = "bold #e0af68"

        t.append("   │  ", style="#3b4261")
        t.append(f"{focus_hint:<45}", style=focus_style)
        t.append("│  m: Inject  s: Split  ?: Help │\n", style="#7982a9")
        t.append("   ╰────────────────────────────────────────────────────────────────────────╯\n", style="#3b4261")
        if is_coordinator:
            t.append("\n   [dim #565f89]Live Coordinator stream active. Press Tab to toggle focus between panes.[/dim #565f89]\n")
        else:
            t.append("\n   [dim #565f89]Live stream active. Commands sent directly to child agy process.[/dim #565f89]\n")
        return t

    def on_mount(self) -> None:
        """Set up a high-frequency polling timer for smooth screen updates."""
        self.set_interval(0.04, self._check_for_updates)

    def on_focus(self) -> None:
        self.post_message(self.TerminalFocusChanged(is_focused=True))
        self.refresh()

    def on_blur(self) -> None:
        self.post_message(self.TerminalFocusChanged(is_focused=False))
        self.refresh()

    def _check_for_updates(self) -> None:
        """Trigger a re-render if new output arrived in the buffer."""
        current_version = self.worker_session.buffer.version
        if current_version != self._last_rendered_version:
            self._last_rendered_version = current_version
            self.refresh()

    def on_resize(self, event: events.Resize) -> None:
        """Sync virtual screen buffer and PTY dimensions with widget size."""
        cols = max(30, event.size.width - 2)
        rows = max(5, event.size.height - 2)
        self.worker_session.buffer.resize(columns=cols, lines=rows)
        if self.worker_session.process:
            self.worker_session.process.resize(columns=cols, lines=rows)

    def on_key(self, event: events.Key) -> None:
        """Handle keystrokes based on current modal state.

        In NORMAL mode: Does not consume keys, allowing them to bubble up to
        WorkspaceScreen for single-key command processing.

        In PTY_INTERACT mode: Raw keystrokes are written directly to worker stdin,
        except Escape (returns to NORMAL mode) and Ctrl+M (opens injection modal).
        """
        # If in NORMAL mode, do NOT consume: allow bubbling to WorkspaceScreen.on_key()
        if not self.is_pty_mode:
            return

        key_name = event.key.lower()

        # 1. Escape: Immediately leave Insert/PTY Mode and return to NORMAL mode
        if key_name in ("escape", "caps_lock"):
            event.stop()
            event.prevent_default()
            self.post_message(self.ModeChangeRequested("NORMAL"))
            return

        # 2. Ctrl+M: Open Directive Injection Modal directly
        if key_name == "ctrl+m":
            event.stop()
            event.prevent_default()
            self.post_message(self.OpenDirectiveRequested())
            return

        # 3. Ctrl+E: Open Agent Configuration Modal directly
        if key_name == "ctrl+e":
            event.stop()
            event.prevent_default()
            self.post_message(self.OpenConfigRequested())
            return

        # 4. Special key mappings
        if key_name in _SPECIAL_KEYS:
            self.worker_session.write(_SPECIAL_KEYS[key_name])
            event.stop()
            event.prevent_default()
            return

        # 4. Regular characters
        if event.character:
            self.worker_session.write(event.character)
            event.stop()
            event.prevent_default()


class WorkerTerminalTab(Widget):
    """Container tab hosting an individual worker agent's terminal session."""

    has_unread: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    WorkerTerminalTab {
        height: 1fr;
        width: 100%;
        layout: vertical;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, worker_session: WorkerSession, mode: str = "NORMAL", **kwargs) -> None:
        super().__init__(**kwargs)
        self.worker_session = worker_session
        self.screen_widget = TerminalScreenWidget(worker_session=worker_session, mode=mode)
        self._toast_timer = None
        self.add_class("worker-terminal-tab")

    def compose(self) -> ComposeResult:
        # 1. Top status line
        with Horizontal(classes="terminal-header"):
            yield Static(self._build_header_text(), id=f"header-text-{self.worker_session.worker_id}")

        # 2. Toast banner for inter-agent injections
        with Vertical(classes="terminal-toast", id=f"toast-{self.worker_session.worker_id}"):
            yield Static("", id=f"toast-text-{self.worker_session.worker_id}")

        # 3. Interactive terminal screen
        yield self.screen_widget

    def on_mount(self) -> None:
        """Register notification listener with worker session."""
        self.worker_session.add_notification_listener(self._on_notification)
        self.set_interval(1.0, self._refresh_header)

    def _build_header_text(self) -> str:
        """Construct the styled header bar text with instance identity and runtime warnings."""
        state = self.worker_session.state
        if state == WorkerProcessState.RUNNING:
            state_str = "[bold #9ece6a]● RUNNING[/]"
        elif state == WorkerProcessState.PAUSED:
            state_str = "[bold #e0af68]⏸ PAUSED[/]"
        elif state == WorkerProcessState.WAITING_INPUT:
            state_str = "[bold #7dcfff]⏳ WAITING INPUT[/]"
        else:
            state_str = "[bold #f7768e]❌ TERMINATED[/]"

        pid_info = f"PID: {self.worker_session.pid}" if self.worker_session.pid else "PID: -"
        instance_name = self.worker_session.assigned_agent or self.worker_session.name or f"agy{self.worker_session.worker_id}"

        # Directive badge
        directive_badge = ""
        if self.worker_session.unread_notifications > 0:
            directive_badge = f" [bold #1a1b26 on #e0af68] 🔔 {self.worker_session.unread_notifications} DIRECTIVE [/]"

        # Runtime Warning badge (e.g. --effort fallback, model unsupported, etc.)
        warning_badge = ""
        if self.worker_session.runtime_warnings:
            latest_warn = self.worker_session.runtime_warnings[-1]
            if "--effort" in latest_warn:
                warn_label = "--effort fallback"
            elif "unknown agent" in latest_warn:
                warn_label = "unknown agent"
            else:
                warn_label = latest_warn[:24]
            warning_badge = f" [bold #1a1b26 on #f7768e] ⚠ Warning: {warn_label} [/]"

        if self.worker_session.role == "coordinator" or str(self.worker_session.worker_id) == "coordinator":
            return (
                f" [bold #1a1b26 on #bb9af7] 🧠 PRIMARY COORDINATOR [/] "
                f"[dim]Instance:[/] [bold #bb9af7]{instance_name}[/] "
                f"[dim]({self.worker_session.model} · {pid_info})[/] "
                f"{state_str}{directive_badge}{warning_badge} "
                f"[italic #7982a9]— {self.worker_session.task}[/]"
            )

        return (
            f" [bold #7aa2f7]● Worker-{self.worker_session.worker_id}[/] "
            f"[dim]Instance:[/] [bold #bb9af7]{instance_name}[/] "
            f"[dim]({self.worker_session.model} · {pid_info})[/] "
            f"{state_str}{directive_badge}{warning_badge} "
            f"[italic #7982a9]— {self.worker_session.task}[/]"
        )

    def update_header_info(self) -> None:
        """Force immediate re-render of tab header and notifications."""
        self._refresh_header()

    def _refresh_header(self) -> None:
        """Periodically update header text."""
        try:
            widget = self.query_one(f"#header-text-{self.worker_session.worker_id}", Static)
            widget.update(self._build_header_text())
        except Exception:
            pass

    def _on_notification(self, session: WorkerSession, formatted_directive: str) -> None:
        """Handle incoming interrupt/injection event from MCP or coordinator."""
        self.app.call_from_thread(self._show_toast, formatted_directive)

    def _show_toast(self, message: str) -> None:
        """Display an immediate visual toast notification banner inside the tab."""
        self.has_unread = True
        self._refresh_header()

        try:
            toast_box = self.query_one(f"#toast-{self.worker_session.worker_id}", Vertical)
            toast_text = self.query_one(f"#toast-text-{self.worker_session.worker_id}", Static)
            toast_text.update(f"[bold #e0af68]⚡ INCOMING DIRECTIVE INJECTED VIA MCP:[/]\n{message.strip()}")
            toast_box.add_class("visible")

            if self._toast_timer:
                self._toast_timer.stop()
            self._toast_timer = self.set_timer(8.0, self._hide_toast)
        except Exception:
            pass

    def _hide_toast(self) -> None:
        """Hide the toast notification banner."""
        try:
            toast_box = self.query_one(f"#toast-{self.worker_session.worker_id}", Vertical)
            toast_box.remove_class("visible")
        except Exception:
            pass

    def on_click(self) -> None:
        """Focus the terminal screen on tab click and clear unread badge."""
        self.screen_widget.focus()
        if self.worker_session.unread_notifications > 0:
            self.worker_session.clear_notifications()
            self._refresh_header()


class WorkerTabPill(Static):
    """Clickable tab pill in the worker tab bar."""

    def __init__(self, worker_id: str, label: str, is_active: bool = False, **kwargs) -> None:
        self.worker_id = worker_id
        self.is_active = is_active
        classes = "worker-tab-pill -active" if is_active else "worker-tab-pill"
        super().__init__(label, classes=classes, **kwargs)

    def on_click(self) -> None:
        self.run_action(f"switch_worker('{self.worker_id}')")


class WorkerNewTabPill(Static):
    """Clickable '+ New (c)' pill at the end of the tab bar."""

    def __init__(self, **kwargs) -> None:
        super().__init__("[bold #9ece6a]+ New (c)[/]", classes="worker-new-pill", **kwargs)

    def on_click(self) -> None:
        self.run_action("new_tab")


class WorkerTabBar(Widget):
    """Visible tab bar showing all active workers: [ 1: Worker-1 (agy) ] [ 2: Worker-2 (agy) ] ... [ + New (c) ]"""

    DEFAULT_CSS = """
    WorkerTabBar {
        dock: top;
        height: 1;
        width: 100%;
        background: #16161e;
        color: #c0caf5;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        active_worker_id: str,
        workers: list[tuple[str, str]],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.active_worker_id = str(active_worker_id)
        self.tab_items = list(workers)

    @staticmethod
    def _format_tab_title(worker_id: str, name: str, is_active: bool) -> str:
        """Format clean, unclipped tab title supporting Unicode and non-ASCII names."""
        clean_name = str(name).strip()
        if clean_name in (f"Worker-{worker_id}", f"Worker {worker_id}", ""):
            title = f"[{worker_id}] agy{worker_id} (Worker-{worker_id})"
        elif clean_name.startswith("agy"):
            title = f"[{worker_id}] {clean_name} (Worker-{worker_id})"
        else:
            title = f"[{worker_id}] {clean_name} · Worker-{worker_id}"

        if is_active:
            return f"[bold #1a1b26 on #7aa2f7] {title} [/]"
        return f"[bold #7aa2f7 on #1f2335] {title} [/]"

    def compose(self) -> ComposeResult:
        with Horizontal(id="worker-tab-strip"):
            for worker_id, name in self.tab_items:
                is_active = (str(worker_id) == str(self.active_worker_id))
                label = self._format_tab_title(str(worker_id), name, is_active)
                yield WorkerTabPill(
                    worker_id=str(worker_id),
                    label=label,
                    is_active=is_active,
                    id=f"tab-pill-{worker_id}",
                )
            yield WorkerNewTabPill(id="tab-pill-new")

    def set_active(self, worker_id: str) -> None:
        """Update active tab highlight."""
        self.active_worker_id = str(worker_id)
        for w_id, name in self.tab_items:
            try:
                pill = self.query_one(f"#tab-pill-{w_id}", WorkerTabPill)
                is_active = (str(w_id) == str(worker_id))
                pill.is_active = is_active
                if is_active:
                    pill.remove_class("-active")
                    pill.add_class("-active")
                else:
                    pill.remove_class("-active")
                pill.update(self._format_tab_title(str(w_id), name, is_active))
            except Exception:
                pass

    def rebuild(self, workers: list[tuple[str, str]], active_worker_id: str) -> None:
        """Re-render the tab bar when workers are added or removed."""
        self.tab_items = list(workers)
        self.active_worker_id = str(active_worker_id)
        try:
            strip = self.query_one("#worker-tab-strip", Horizontal)
            strip.remove_children()
            for worker_id, name in self.tab_items:
                is_active = (str(worker_id) == str(self.active_worker_id))
                label = self._format_tab_title(str(worker_id), name, is_active)
                strip.mount(
                    WorkerTabPill(
                        worker_id=str(worker_id),
                        label=label,
                        is_active=is_active,
                        id=f"tab-pill-{worker_id}",
                    )
                )
            strip.mount(WorkerNewTabPill(id="tab-pill-new"))
        except Exception:
            pass

