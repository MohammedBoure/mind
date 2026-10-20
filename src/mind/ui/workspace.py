"""Workspace screen — the main TUI layout with agent panes, PTY terminals, and MCP bridge."""

from __future__ import annotations

from datetime import datetime
import random

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import TabbedContent, TabPane

from mind.core.terminal_manager import TerminalManager, WorkerSession
from mind.events import AgentLogAppend, InterruptReceived
from mind.mcp.runner import start_background_mcp_server, stop_background_mcp_server
from mind.state.mock_data import (
    get_mock_agents,
    get_mock_log_stream,
    get_random_interrupt_message,
)
from mind.state.models import AgentInfo, AgentStatus, InterAgentMessage, LogEntry, MessagePriority
from mind.ui.agent_pane import AgentLogPane
from mind.ui.bottom_bar import BottomBar
from mind.ui.directive_modal import DirectiveModal
from mind.ui.header_bar import HeaderBar
from mind.ui.interrupt_banner import InterruptBanner
from mind.ui.terminal_tab import TerminalScreenWidget, WorkerTerminalTab


class WorkspaceScreen(Screen):
    """Main workspace screen with split-pane agent views.

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

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("question_mark", "show_help", "Help"),
        ("ctrl+m", "open_directive_modal", "Inject Directive"),
        ("ctrl+c", "interrupt_active", "Interrupt"),
        ("m", "mock_interrupt", "Mock Interrupt"),
        ("n", "new_tab", "New Tab"),
        ("s", "toggle_split", "Toggle Split"),
        ("tab", "focus_next", "Focus Next"),
        ("escape", "go_back", "Back"),
        ("alt+1", "switch_worker('1')", "Worker 1"),
        ("alt+2", "switch_worker('2')", "Worker 2"),
        ("alt+3", "switch_worker('3')", "Worker 3"),
        ("alt+4", "switch_worker('4')", "Worker 4"),
        ("alt+5", "switch_worker('5')", "Worker 5"),
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
                            tab_widget = WorkerTerminalTab(worker_session=session)
                            self._worker_tabs[worker_id] = tab_widget

                            with TabPane(f"{agent.name}", id=f"worker-tab-{worker_id}"):
                                yield tab_widget

        # 4. Interactive Bottom Status Bar
        yield BottomBar(worker_count=worker_count)

    def on_mount(self) -> None:
        """Initialize background MCP server, notification listeners, and auto-focus."""
        # Start embedded MCP server in the background
        start_background_mcp_server(host="127.0.0.1", port=8765)

        # Connect global notification listener to show banner on MCP injections
        self._terminal_manager.add_notification_listener(self._on_mcp_directive_injected)

        # Start primary agent coordination stream
        self._stream_timer = self.set_interval(2.5, self._emit_primary_log)

        # Auto-focus the active terminal widget after layout stabilization
        self.set_timer(0.15, self._auto_focus_terminal)

    def on_unmount(self) -> None:
        """Clean up background tasks on unmount."""
        if self._stream_timer:
            self._stream_timer.stop()
        stop_background_mcp_server()

    # ── Focus & Mode Management ────────────────────────────────────

    @on(TerminalScreenWidget.TerminalFocusChanged)
    def on_terminal_focus_changed(self, event: TerminalScreenWidget.TerminalFocusChanged) -> None:
        """Update header and bottom bar mode indicator when terminal gains/loses focus."""
        mode = "PTY INTERACT" if event.is_focused else "NORMAL"
        try:
            self.query_one(HeaderBar).mode = mode
        except Exception:
            pass
        try:
            self.query_one(BottomBar).mode = mode
        except Exception:
            pass

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

    # ── Event Callbacks ────────────────────────────────────────────

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

    # ── Actions ───────────────────────────────────────────────────

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
                    self.notify(f"⚡ Interrupted Worker-{worker_id}", severity="warning")
                    return
        except Exception:
            pass

        workers = self._terminal_manager.list_workers()
        if workers:
            workers[0].interrupt()
            self.notify(f"⚡ Interrupted {workers[0].name}", severity="warning")

    def action_next_worker(self) -> None:
        """Cycle to the next worker tab."""
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

    def action_mock_interrupt(self) -> None:
        """Trigger an interrupt directive test through the worker terminal session."""
        workers = self._terminal_manager.list_workers()
        if workers:
            target = random.choice(workers)
            target.interrupt_and_inject(
                sender_id="Primary-Agent",
                message="Workflow update: Pause current task and verify dependency contracts.",
                priority="high",
            )
        else:
            message = get_random_interrupt_message()
            banner = self.query_one(InterruptBanner)
            banner.show_interrupt(message)

    def action_switch_worker(self, worker_id: str) -> None:
        """Switch active worker tab and focus its terminal."""
        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            tabs.active = f"worker-tab-{worker_id}"
            tab_widget = self._worker_tabs.get(str(worker_id))
            if tab_widget and tab_widget.screen_widget:
                tab_widget.screen_widget.focus()
        except Exception:
            pass

    def action_new_tab(self) -> None:
        """Add a new worker agent tab dynamically."""
        new_id = str(len(self._agents))
        new_agent = AgentInfo(
            id=int(new_id),
            name=f"Worker-{new_id}",
            role="worker",
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
        tab_widget = WorkerTerminalTab(worker_session=session)
        self._worker_tabs[new_id] = tab_widget

        try:
            tabs = self.query_one("#worker-tabs", TabbedContent)
            tabs.add_pane(TabPane(f"{new_agent.name}", tab_widget, id=f"worker-tab-{new_id}"))
            # Update counts in header and bottom bar
            active_worker_count = len(self._agents) - 1
            self.query_one(HeaderBar).worker_count = active_worker_count
            self.query_one(BottomBar).worker_count = active_worker_count
            self.notify(f"Spawned {new_agent.name} with live PTY session.")
        except Exception:
            pass

    def action_toggle_split(self) -> None:
        """Toggle between horizontal and vertical split layout."""
        container = self.query_one("#workspace-container")
        self._is_horizontal = not self._is_horizontal
        if self._is_horizontal:
            container.styles.layout = "horizontal"
            self.notify("Layout: side-by-side")
        else:
            container.styles.layout = "vertical"
            self.notify("Layout: stacked")

    def action_go_back(self) -> None:
        """Return to session picker screen."""
        if self._stream_timer:
            self._stream_timer.stop()
        stop_background_mcp_server()
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()
