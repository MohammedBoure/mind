"""Workspace screen — the main TUI layout with agent panes, PTY terminals, and MCP bridge.

Implements a strict Vim-like Modal System:
- NORMAL mode (Command Mode): Single-key navigation (1..9, h/l, i, m, s, c, x, ?, q).
- PTY_INTERACT mode (Insert Mode): Direct raw stdin to child agy process; Esc to exit.
"""

from __future__ import annotations

from datetime import datetime
import random

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import TabbedContent, TabPane

from mind.core.terminal_manager import TerminalManager, WorkerSession
from mind.mcp.runner import start_background_mcp_server, stop_background_mcp_server
from mind.state.mock_data import (
    get_mock_agents,
    get_mock_log_stream,
    get_random_interrupt_message,
)
from mind.state.models import AgentInfo, AgentRole, AgentStatus, InterAgentMessage, LogEntry, MessagePriority
from mind.ui.agent_pane import AgentLogPane
from mind.ui.bottom_bar import BottomBar
from mind.ui.directive_modal import DirectiveModal
from mind.ui.header_bar import HeaderBar
from mind.ui.interrupt_banner import InterruptBanner
from mind.ui.terminal_tab import TerminalScreenWidget, WorkerTerminalTab


class WorkspaceScreen(Screen):
    """Main workspace screen with split-pane agent views and Vim modal system.

    Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │ HeaderBar: [mind] | [session] | [mode] | [mcp] | [workers]  │
    ├─────────────────────────────────────────────────────────────┤
    │ InterruptBanner (hidden until triggered)                    │
    ├──────────────────────────────┬──────────────────────────────┤
    │ Primary Agent Pane           │ Interactive Worker PTYs      │
    │ (left / coordinator stream)  │ (right / tabbed terminals)   │
    ├──────────────────────────────┴──────────────────────────────┤
    │ BottomBar: Mode | Clickable Action Pills | PTY status       │
    └─────────────────────────────────────────────────────────────┘
    """

    mode: reactive[str] = reactive("NORMAL")

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("question_mark", "show_help", "Help"),
        ("i", "enter_pty", "Enter PTY"),
        ("enter", "enter_pty", "Enter PTY"),
        ("escape", "enter_normal", "Normal Mode"),
        ("ctrl+m", "open_directive_modal", "Inject Directive"),
        ("ctrl+c", "interrupt_active", "Interrupt"),
        ("h", "prev_worker", "Prev Worker"),
        ("l", "next_worker", "Next Worker"),
        ("c", "new_tab", "New Worker Tab"),
        ("x", "close_active_tab", "Close Worker Tab"),
        ("s", "toggle_split", "Toggle Split"),
        ("tab", "focus_next", "Focus Next"),
    ]

    def __init__(
        self,
        session_name: str = "default",
        agent_count: int = 3,
        goal: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._session_name = session_name
        self._agent_count = max(agent_count, 1)
        self._goal = goal
        self._agents: list[AgentInfo] = []
        self._worker_tabs: dict[str, WorkerTerminalTab] = {}
        self._is_horizontal = True
        self._stream_timer = None
        self._terminal_manager = TerminalManager.get_instance()

    def compose(self) -> ComposeResult:
        self._agents = get_mock_agents(self._agent_count)
        worker_count = max(len(self._agents) - 1, 0)

        # 1. Streamlined Header Bar
        yield HeaderBar(
            session_name=self._session_name,
            worker_count=worker_count,
            mode=self.mode,
        )

        # 2. Inter-agent interrupt banner (hidden until directive arrives)
        yield InterruptBanner()

        # 3. Main Workspace: Primary coordinator pane (left) + Worker PTYs (right)
        primary = self._agents[0]
        primary_logs = get_mock_log_stream(primary.id)
        primary_pane = AgentLogPane(
            agent=primary,
            logs=primary_logs,
            pane_id="primary-pane",
        )

        with Horizontal(id="workspace-container"):
            yield primary_pane

            # Worker interactive PTY terminal panes
            if len(self._agents) > 1:
                with Vertical(id="workers-pane"):
                    with TabbedContent(id="worker-tabs"):
                        for agent in self._agents[1:]:
                            worker_id = str(agent.id)
                            # Create or retrieve real PTY worker session
                            session = self._terminal_manager.create_worker(
                                worker_id=worker_id,
                                name=agent.name,
                                model=agent.model,
                                task=agent.task,
                                autostart=True,
                            )
                            tab_widget = WorkerTerminalTab(worker_session=session, mode=self.mode)
                            self._worker_tabs[worker_id] = tab_widget

                            with TabPane(f"{agent.name}", id=f"worker-tab-{worker_id}"):
                                yield tab_widget

        # 4. Interactive Bottom Status Bar
        yield BottomBar(worker_count=worker_count, mode=self.mode)

    def on_mount(self) -> None:
        """Initialize background MCP server, notification listeners, and auto-focus."""
        start_background_mcp_server(host="127.0.0.1", port=8765)
        self._terminal_manager.add_notification_listener(self._on_mcp_directive_injected)
        self._stream_timer = self.set_interval(2.5, self._emit_primary_log)
        self.set_timer(0.15, self._auto_focus_terminal)

    def on_unmount(self) -> None:
        """Clean up background tasks on unmount."""
        if self._stream_timer:
            self._stream_timer.stop()
        stop_background_mcp_server()

    # ── Centralized Mode Management ────────────────────────────────

    def watch_mode(self, new_mode: str) -> None:
        """Propagate mode changes to HeaderBar, BottomBar, and child terminal widgets."""
        try:
            self.query_one(HeaderBar).mode = new_mode
        except Exception:
            pass

        try:
            self.query_one(BottomBar).mode = new_mode
        except Exception:
            pass

        for tab in self._worker_tabs.values():
            if tab.screen_widget:
                tab.screen_widget.mode = new_mode
                tab.screen_widget.refresh()

    def _safe_notify(self, message: str, severity: str = "information", timeout: float = 2.0) -> None:
        """Post a notification if active app context exists; fail silently otherwise."""
        try:
            self.notify(message, severity=severity, timeout=timeout)
        except Exception:
            pass

    def action_enter_pty(self) -> None:
        """Switch to PTY_INTERACT (Insert) mode and focus active terminal."""
        self.mode = "PTY_INTERACT"
        self._auto_focus_terminal()
        self._safe_notify("⌨ PTY Mode Active (Press Esc for Normal)", timeout=1.5)

    def action_enter_normal(self) -> None:
        """Switch to NORMAL (Vim Command) mode."""
        self.mode = "NORMAL"
        self._auto_focus_terminal()
        self._safe_notify("🔍 Normal Mode Active (Press 'i' to type)", timeout=1.5)

    @on(TerminalScreenWidget.ModeChangeRequested)
    def on_mode_change_requested(self, event: TerminalScreenWidget.ModeChangeRequested) -> None:
        """Handle request from terminal widget to switch mode (e.g. Escape pressed)."""
        if event.target_mode == "NORMAL":
            self.action_enter_normal()
        else:
            self.action_enter_pty()

    @on(TerminalScreenWidget.OpenDirectiveRequested)
    def on_open_directive_requested(self, event: TerminalScreenWidget.OpenDirectiveRequested) -> None:
        """Handle directive modal request triggered while in PTY mode."""
        self.action_open_directive_modal()

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Auto-focus child terminal when switching tabs."""
        if event.pane and event.pane.id and event.pane.id.startswith("worker-tab-"):
            worker_id = event.pane.id.replace("worker-tab-", "")
            tab_widget = self._worker_tabs.get(worker_id)
            if tab_widget and tab_widget.screen_widget:
                self.set_timer(0.05, tab_widget.screen_widget.focus)

    def _auto_focus_terminal(self) -> None:
        """Focus the currently active worker terminal screen."""
        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            active_pane = tabs.active
            if active_pane and active_pane.startswith("worker-tab-"):
                worker_id = active_pane.replace("worker-tab-", "")
                tab_widget = self._worker_tabs.get(worker_id)
                if tab_widget and tab_widget.screen_widget:
                    tab_widget.screen_widget.focus()
                    return
        except Exception:
            pass

        # Fallback to the first available worker screen widget
        for tab in self._worker_tabs.values():
            if tab.screen_widget:
                tab.screen_widget.focus()
                break

    # ── Vim Modal Key Interception ─────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        """Intercept single-key commands in NORMAL mode and prevent leaking to subprocess."""
        # If in PTY_INTERACT mode, only Escape switches mode
        if self.mode in ("PTY_INTERACT", "PTY"):
            if event.key.lower() in ("escape", "caps_lock"):
                self.action_enter_normal()
                event.stop()
                event.prevent_default()
            return

        # ── NORMAL MODE COMMAND INTERCEPTION ──
        key = event.key.lower()
        char = event.character or ""

        # 1. '1'..'9': Jump directly to Worker tab N
        if (key in "123456789" or char in "123456789") and len(key) == 1:
            worker_num = key if key in "123456789" else char
            self.action_switch_worker(worker_num)
            event.stop()
            event.prevent_default()
            return

        # 2. 'h': Switch to previous worker tab
        if key == "h" or char == "h":
            self.action_prev_worker()
            event.stop()
            event.prevent_default()
            return

        # 3. 'l': Switch to next worker tab
        if key == "l" or char == "l":
            self.action_next_worker()
            event.stop()
            event.prevent_default()
            return

        # 4. 'i', 'enter', 'a': Enter PTY_INTERACT (Insert) mode
        if key in ("i", "enter", "a") or char in ("i", "a"):
            self.action_enter_pty()
            event.stop()
            event.prevent_default()
            return

        # 5. 'm': Open Directive Injection Modal
        if key == "m" or char == "m":
            self.action_open_directive_modal()
            event.stop()
            event.prevent_default()
            return

        # 6. 's': Toggle split layout orientation
        if key == "s" or char == "s":
            self.action_toggle_split()
            event.stop()
            event.prevent_default()
            return

        # 7. 'c': Spawn a new worker agent tab
        if key == "c" or char == "c":
            self.action_new_tab()
            event.stop()
            event.prevent_default()
            return

        # 8. 'x': Terminate / Close active worker tab
        if key == "x" or char == "x":
            self.action_close_active_tab()
            event.stop()
            event.prevent_default()
            return

        # 9. '?': Toggle Help Modal
        if key in ("question_mark", "?") or char == "?":
            self.action_show_help()
            event.stop()
            event.prevent_default()
            return

        # 10. 'q': Quit application
        if key == "q" or char == "q":
            self.action_quit()
            event.stop()
            event.prevent_default()
            return

        # 11. 'tab': Cycle focus between Primary Agent pane and Worker Terminal
        if key == "tab":
            self.action_focus_next()
            event.stop()
            event.prevent_default()
            return

        # Prevent any unmapped keys from leaking in NORMAL mode
        event.stop()
        event.prevent_default()

    # ── Inter-Agent Events ─────────────────────────────────────────

    def _on_mcp_directive_injected(self, worker: WorkerSession, formatted_directive: str) -> None:
        """Handle inter-agent message injected via MCP tool call."""
        msg = InterAgentMessage(
            sender="MCP Bridge",
            receiver=worker.name,
            priority=MessagePriority.HIGH,
            directive=formatted_directive.strip(),
        )
        try:
            banner = self.query_one(InterruptBanner)
            banner.show_interrupt(msg)
        except Exception:
            pass

    def _emit_primary_log(self) -> None:
        """Emit simulated coordination thoughts and MCP tool invocations for Primary Agent."""
        mock_lines = [
            ("thought", "Primary coordinator monitoring active worker sessions..."),
            ("tool_call", "→ mcp::list_workers()"),
            ("result", f"✓ {max(len(self._agents)-1, 0)} active workers verified healthy."),
            ("thought", "Evaluating worker progress on assigned tasks."),
            ("tool_call", "→ mcp::get_terminal_screen('1', lines=10)"),
            ("result", "✓ Worker-1 terminal buffer inspected. Output steady."),
            ("thought", "All sub-agents executing within parameters."),
            ("info", "Syncing multi-agent state with MCP bridge."),
            ("thought", "Checking for pending inter-agent interrupts..."),
        ]

        entry_type, content = random.choice(mock_lines)
        entry = LogEntry(
            timestamp=datetime.now(),
            source="Primary-Agent",
            content=content,
            entry_type=entry_type,
        )

        try:
            primary_pane = self.query_one("#primary-pane", AgentLogPane)
            primary_pane.append_log(entry)
        except Exception:
            pass

    # ── Workspace Actions ──────────────────────────────────────────

    def action_quit(self) -> None:
        """Exit the application and stop background processes."""
        self._terminal_manager.stop_all()
        stop_background_mcp_server()
        self.app.exit()

    def action_show_help(self) -> None:
        """Show the help modal dialog."""
        from mind.ui.help_modal import HelpModal

        self.app.push_screen(HelpModal())

    def action_open_directive_modal(self) -> None:
        """Open interactive directive injection modal."""
        self.app.push_screen(DirectiveModal())

    def action_interrupt_active(self) -> None:
        """Send immediate interrupt (SIGINT/Ctrl+C) to the currently selected worker."""
        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            active_id = tabs.active
            if active_id and active_id.startswith("worker-tab-"):
                worker_id = active_id.replace("worker-tab-", "")
                worker = self._terminal_manager.get_worker(worker_id)
                if worker:
                    worker.interrupt()
                    self._safe_notify(f"⚡ Interrupted Worker-{worker_id}", severity="warning")
                    return
        except Exception:
            pass

        workers = self._terminal_manager.list_workers()
        if workers:
            workers[0].interrupt()
            self._safe_notify(f"⚡ Interrupted {workers[0].name}", severity="warning")

    def action_next_worker(self) -> None:
        """Switch to next worker tab ('l' in NORMAL mode)."""
        if len(self._agents) <= 1:
            return
        worker_ids = [str(a.id) for a in self._agents[1:]]
        if not worker_ids:
            return
        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            current_pane_id = tabs.active
            current_id = current_pane_id.replace("worker-tab-", "") if current_pane_id else worker_ids[0]
            idx = worker_ids.index(current_id) if current_id in worker_ids else -1
            next_id = worker_ids[(idx + 1) % len(worker_ids)]
            self.action_switch_worker(next_id)
        except Exception:
            pass

    def action_prev_worker(self) -> None:
        """Switch to previous worker tab ('h' in NORMAL mode)."""
        if len(self._agents) <= 1:
            return
        worker_ids = [str(a.id) for a in self._agents[1:]]
        if not worker_ids:
            return
        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            current_pane_id = tabs.active
            current_id = current_pane_id.replace("worker-tab-", "") if current_pane_id else worker_ids[0]
            idx = worker_ids.index(current_id) if current_id in worker_ids else 0
            prev_id = worker_ids[(idx - 1) % len(worker_ids)]
            self.action_switch_worker(prev_id)
        except Exception:
            pass

    def action_switch_worker(self, worker_id: str) -> None:
        """Switch active worker tab and focus its terminal."""
        target_pane_id = f"worker-tab-{worker_id}"
        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            tabs.active = target_pane_id
            tab_widget = self._worker_tabs.get(str(worker_id))
            if tab_widget and tab_widget.screen_widget:
                tab_widget.screen_widget.focus()
        except Exception:
            pass

    def action_close_active_tab(self) -> None:
        """Terminate and close active worker tab ('x' in NORMAL mode)."""
        if len(self._agents) <= 2:
            self._safe_notify("At least one worker agent tab must remain active.", severity="warning")
            return

        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            active_pane_id = tabs.active
            if not active_pane_id or not active_pane_id.startswith("worker-tab-"):
                return

            worker_id = active_pane_id.replace("worker-tab-", "")
            worker_session = self._terminal_manager.get_worker(worker_id)
            if worker_session:
                worker_session.terminate()

            tabs.remove_pane(active_pane_id)
            self._worker_tabs.pop(worker_id, None)
            self._agents = [a for a in self._agents if str(a.id) != worker_id]

            # Update count in status bars
            remaining_count = max(len(self._agents) - 1, 0)
            self.query_one(HeaderBar).worker_count = remaining_count
            self.query_one(BottomBar).worker_count = remaining_count

            # Activate first available remaining tab
            remaining_ids = [str(a.id) for a in self._agents[1:]]
            if remaining_ids:
                self.action_switch_worker(remaining_ids[0])

            self._safe_notify(f"Closed worker tab {worker_id}", severity="information")
        except Exception as exc:
            self._safe_notify(f"Could not close worker tab: {exc}", severity="error")

    def action_focus_next(self) -> None:
        """Toggle focus between primary agent pane and active worker terminal."""
        focused = self.focused
        if isinstance(focused, TerminalScreenWidget):
            try:
                primary = self.query_one("#primary-pane", AgentLogPane)
                primary.focus()
            except Exception:
                self.focus_next()
        else:
            self._auto_focus_terminal()

    def action_new_tab(self) -> None:
        """Add a new worker agent tab dynamically ('c' in NORMAL mode)."""
        existing_ids = {a.id for a in self._agents}
        next_id_int = max(existing_ids, default=0) + 1
        new_id = str(next_id_int)
        new_agent = AgentInfo(
            id=next_id_int,
            name=f"Worker-{new_id}",
            role=AgentRole.WORKER,
            status=AgentStatus.RUNNING,
            model="gpt-4o-mini",
            task="General tasks",
        )
        self._agents.append(new_agent)

        session = self._terminal_manager.create_worker(
            worker_id=new_id,
            name=new_agent.name,
            model=new_agent.model,
            task=new_agent.task,
            autostart=True,
        )
        tab_widget = WorkerTerminalTab(worker_session=session, mode=self.mode)
        self._worker_tabs[new_id] = tab_widget

        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            tabs.add_pane(TabPane(f"{new_agent.name}", tab_widget, id=f"worker-tab-{new_id}"))
            active_worker_count = len(self._agents) - 1
            self.query_one(HeaderBar).worker_count = active_worker_count
            self.query_one(BottomBar).worker_count = active_worker_count
            self.action_switch_worker(new_id)
            self._safe_notify(f"Spawned {new_agent.name} with live PTY session.")
        except Exception:
            pass

    def action_toggle_split(self) -> None:
        """Toggle between horizontal and vertical split layout ('s' in NORMAL mode)."""
        container = self.query_one("#workspace-container")
        self._is_horizontal = not self._is_horizontal
        if self._is_horizontal:
            container.styles.layout = "horizontal"
            self._safe_notify("Layout: side-by-side")
        else:
            container.styles.layout = "vertical"
            self._safe_notify("Layout: stacked")

    def action_go_back(self) -> None:
        """Return to session picker screen."""
        if self._stream_timer:
            self._stream_timer.stop()
        stop_background_mcp_server()
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()
