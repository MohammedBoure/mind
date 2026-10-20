"""Interactive Terminal Tab widget for Textual TUI.

Hosts a real PTY session running agy (or shell), renders the virtual screen
buffer with full ANSI styles, captures user keystrokes for direct interactive
control, and displays visual toast badges upon MCP directive injections.
Implements Vim-like modal input (NORMAL vs PTY_INTERACT).
"""

from __future__ import annotations

import sys
import time
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from mind.core.terminal_manager import WorkerProcessState, WorkerSession
from mind.ui.clipboard import copy_to_clipboard, get_clipboard_text


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
        self._pending_esc: bool = False
        self._last_esc_time: float = 0.0
        self._esc_timer = None
        self._is_dragging: bool = False
        self._select_start: tuple[int, int] | None = None
        self._select_end: tuple[int, int] | None = None
        self.add_class("terminal-screen")
        self._sync_mode_classes()

    @property
    def has_selection(self) -> bool:
        """Return True if a non-empty text region is currently highlighted."""
        if not self._select_start or not self._select_end:
            return False
        return self._select_start != self._select_end

    def clear_selection(self) -> None:
        """Clear active text selection."""
        self._select_start = None
        self._select_end = None
        self._is_dragging = False
        self.refresh()

    def get_selected_text(self) -> str:
        """Extract text within the active selection coordinates."""
        if not self.has_selection or not self._select_start or not self._select_end:
            return ""
        lines = self.worker_session.buffer.get_visible_lines()
        if not lines:
            return ""

        sx, sy = self._select_start
        ex, ey = self._select_end

        if (sy, sx) > (ey, ex):
            y1, x1, y2, x2 = ey, ex, sy, sx
        else:
            y1, x1, y2, x2 = sy, sx, ey, ex

        y1 = max(0, min(y1, len(lines) - 1))
        y2 = max(0, min(y2, len(lines) - 1))

        if y1 == y2:
            line = lines[y1]
            return line[min(x1, x2):max(x1, x2)].rstrip()

        extracted: list[str] = []
        first_line = lines[y1]
        extracted.append(first_line[min(x1, len(first_line)):].rstrip())
        for y in range(y1 + 1, y2):
            extracted.append(lines[y].rstrip())
        last_line = lines[y2]
        extracted.append(last_line[:min(x2, len(last_line))].rstrip())

        return "\n".join(extracted).strip()

    def _get_safe_app(self) -> Any:
        try:
            return self.app
        except Exception:
            return None

    def copy_selection_or_buffer(self) -> str:
        """Copy active selection or recent visible terminal buffer lines to OS clipboard."""
        text = self.get_selected_text()
        if text:
            desc = f"selection ({len(text)} chars)"
        else:
            text = self.worker_session.get_screen(lines=50).strip()
            desc = f"terminal buffer ({len(text)} chars)"

        if text:
            copy_to_clipboard(text, app=self._get_safe_app())
            self._safe_notify(f"📋 Copied {desc} to clipboard", timeout=1.5)
        else:
            self._safe_notify("Buffer is empty", severity="warning", timeout=1.0)
        return text

    def _safe_notify(self, message: str, severity: str = "information", timeout: float = 1.5) -> None:
        try:
            self.notify(message, severity=severity, timeout=timeout)
        except Exception:
            pass

    def _flush_pending_esc(self, send: bool = True) -> None:
        """Clear pending escape timer and optionally forward bare Escape to child PTY."""
        if self._esc_timer is not None:
            try:
                self._esc_timer.stop()
            except Exception:
                pass
            self._esc_timer = None
        if self._pending_esc:
            self._pending_esc = False
            if send:
                self.worker_session.write("\x1b")

    def _on_esc_timeout(self) -> None:
        """Timer elapsed without a 2nd Escape: pass bare Escape directly to child PTY."""
        if self._pending_esc:
            self._pending_esc = False
            self.worker_session.write("\x1b")

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
            focus_hint = "[ ⌨ PTY INTERACT (Press Esc Esc or Ctrl+B for Outer Normal) ]"
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
        self._flush_pending_esc(send=True)
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

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Handle mouse click and begin drag selection."""
        if event.button == 1:
            self._is_dragging = True
            self._select_start = (event.x, event.y)
            self._select_end = (event.x, event.y)
        elif event.button == 3:
            # Right-click: Copy active selection or entire screen buffer to OS clipboard
            if self.has_selection:
                selected = self.get_selected_text()
                if selected:
                    copy_to_clipboard(selected, app=self._get_safe_app())
                    self._safe_notify(f"📋 Copied selection to clipboard ({len(selected)} chars)", timeout=1.5)
                self.clear_selection()
            else:
                self.copy_selection_or_buffer()
            event.stop()
            event.prevent_default()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Update selection boundary during mouse drag."""
        if self._is_dragging:
            self._select_end = (event.x, event.y)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """Finalize mouse selection and automatically synchronize to clipboard."""
        if event.button == 1 and self._is_dragging:
            self._is_dragging = False
            self._select_end = (event.x, event.y)
            if self.has_selection:
                text = self.get_selected_text()
                if text:
                    copy_to_clipboard(text, app=self._get_safe_app())
                    self._safe_notify(f"📋 Copied selection to clipboard ({len(text)} chars)", timeout=1.5)

    def on_key(self, event: events.Key) -> None:
        """Handle keystrokes based on current modal state.

        In NORMAL mode: Does not consume keys, allowing single-key navigation commands
        to bubble up to WorkspaceScreen.

        In PTY_INTERACT mode:
        - Dedicated leader keys (Ctrl+B, F12, Ctrl+]) and double Escape (Esc Esc within 350ms)
          switch back to mind's outer NORMAL mode.
        - Bare single Escape and all standard keystrokes/arrows pass directly to the child PTY,
          preserving antigravity's internal Vim modal editor and line navigation without interception.
        - Ctrl+Shift+C explicitly copies active selection or screen buffer to OS clipboard.
        - Ctrl+M and Ctrl+E trigger directive and config modals.
        """
        key_name = event.key.lower()

        # 0. Global Clipboard Copy shortcut: Ctrl+Shift+C works in both modes
        if key_name in ("ctrl+shift+c", "ctrl+shift+insert"):
            self.copy_selection_or_buffer()
            event.stop()
            event.prevent_default()
            return

        # In NORMAL mode: do not consume keys; allow bubbling to WorkspaceScreen.on_key()
        if not self.is_pty_mode:
            return

        # 0.1 Explicit Clipboard Paste: Ctrl+V or Shift+Insert
        if key_name in ("ctrl+v", "shift+insert"):
            event.stop()
            event.prevent_default()
            clip_text = get_clipboard_text()
            if clip_text:
                # Strip rogue extended scancodes (\xe0 / à) from keyboard buffer
                clean_text = clip_text.lstrip("\xe0")
                self.worker_session.write(clean_text)
            return

        # 0.2 Filter standalone modifier, lock, and dead keys to avoid leaked scancodes / rogue 'à'
        _MODIFIER_KEYS = {
            "shift", "left_shift", "right_shift",
            "ctrl", "left_ctrl", "right_ctrl",
            "alt", "left_alt", "right_alt", "alt_graph",
            "meta", "left_meta", "right_meta",
            "caps_lock", "num_lock", "scroll_lock",
            "insert", "menu", "print_screen",
            "pause", "pause_break",
        }
        if key_name in _MODIFIER_KEYS:
            event.stop()
            event.prevent_default()
            return

        # 1. Leader / Prefix keys for instant escape to outer NORMAL mode (0ms delay)
        if key_name in ("ctrl+b", "f12", "ctrl+right_square_bracket", "ctrl+]"):
            self._flush_pending_esc(send=False)
            event.stop()
            event.prevent_default()
            self.post_message(self.ModeChangeRequested("NORMAL"))
            return

        # 2. Escape handling: Double Escape (Esc Esc within 350ms) escapes to outer NORMAL mode;
        #    Single Escape passes bare '\x1b' directly to the child PTY (antigravity vim prompt).
        if key_name in ("escape", "caps_lock"):
            event.stop()
            event.prevent_default()
            now = time.time()
            if self._pending_esc and (now - self._last_esc_time <= 0.35):
                # Second Escape in quick succession -> Esc Esc detected!
                self._flush_pending_esc(send=False)
                self.post_message(self.ModeChangeRequested("NORMAL"))
                return

            # First Escape: flush any prior pending escape, then buffer this one
            self._flush_pending_esc(send=True)
            self._pending_esc = True
            self._last_esc_time = now
            try:
                self._esc_timer = self.set_timer(0.35, self._on_esc_timeout)
            except Exception:
                pass
            return

        # Any other key arriving flushes the pending Escape first to child PTY
        if self._pending_esc:
            self._flush_pending_esc(send=True)

        # 3. Ctrl+M: Open Directive Injection Modal directly
        if key_name == "ctrl+m":
            event.stop()
            event.prevent_default()
            self.post_message(self.OpenDirectiveRequested())
            return

        # 4. Ctrl+E: Open Agent Configuration Modal directly
        if key_name == "ctrl+e":
            event.stop()
            event.prevent_default()
            self.post_message(self.OpenConfigRequested())
            return

        # 5. Special key mappings (arrows, enter, backspace, tab, etc.)
        if key_name in _SPECIAL_KEYS:
            self.worker_session.write(_SPECIAL_KEYS[key_name])
            event.stop()
            event.prevent_default()
            return

        # 6. Filter out null characters and accidental rogue 'à' from modifier/navigation keys
        if event.character == "\x00":
            event.stop()
            event.prevent_default()
            return

        if event.character == "à" and key_name not in ("à", "0"):
            event.stop()
            event.prevent_default()
            return

        # 7. Regular characters
        if event.character and len(event.character) == 1:
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
        self._alarm_badge: str = ""
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

        # Alarm badge (e.g. Worker-1 Finished / Idle)
        alarm_badge = ""
        if getattr(self, "_alarm_badge", ""):
            alarm_badge = f" [bold #1a1b26 on #e0af68] {self._alarm_badge} [/]"

        if self.worker_session.role == "coordinator" or str(self.worker_session.worker_id) == "coordinator":
            return (
                f" [bold #1a1b26 on #bb9af7] 🧠 PRIMARY COORDINATOR [/] "
                f"[dim]Instance:[/] [bold #bb9af7]{instance_name}[/] "
                f"[dim]({self.worker_session.model} · {pid_info})[/] "
                f"{state_str}{directive_badge}{warning_badge}{alarm_badge} "
                f"[italic #7982a9]— {self.worker_session.task}[/]"
            )

        return (
            f" [bold #7aa2f7]● Worker-{self.worker_session.worker_id}[/] "
            f"[dim]Instance:[/] [bold #bb9af7]{instance_name}[/] "
            f"[dim]({self.worker_session.model} · {pid_info})[/] "
            f"{state_str}{directive_badge}{warning_badge}{alarm_badge} "
            f"[italic #7982a9]— {self.worker_session.task}[/]"
        )

    def set_alarm_badge(self, badge_text: str) -> None:
        """Display an event or alarm notification badge in the tab header."""
        self._alarm_badge = badge_text
        self._refresh_header()

    def clear_alarm_badge(self) -> None:
        """Clear active alarm badge."""
        self._alarm_badge = ""
        self._refresh_header()

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

