"""Workspace screen — the main TUI layout with agent panes, PTY terminals, and MCP bridge.

Implements a strict Vim-like Modal System:
- NORMAL mode (Command Mode): Single-key navigation (1..9, h/l, i, m, s, c, x, ?, q).
- PTY_INTERACT mode (Insert Mode): Direct raw stdin to child agy process; Esc to exit.
Features visible agent tabs [ 1: Worker-1 (agy) ] [ + New (c) ], split-view toggling ('s'),
and task assignment dispatcher ('m').
"""

from __future__ import annotations

from datetime import datetime
import os
import random
import shutil
import sys
import time
from typing import Any

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import ContentSwitcher

from mind.core.terminal_manager import TerminalManager, WorkerSession
from mind.mcp.runner import start_background_mcp_server, stop_background_mcp_server
from mind.state.mock_data import (
    get_mock_agents,
    get_random_interrupt_message,
)
from mind.state.models import AgentInfo, AgentRole, AgentStatus, InterAgentMessage, MessagePriority
from mind.core.directives import (
    load_directive,
    open_directive_in_editor,
    resolve_directive_path,
    save_directive,
)
from mind.core.session_storage import record_session_activity
from mind.ui.agent_config_modal import AgentConfigModal
from mind.ui.bottom_bar import BottomBar
from mind.ui.directive_editor_modal import DirectiveEditorModal
from mind.ui.directive_modal import DirectiveModal
from mind.ui.header_bar import HeaderBar
from mind.ui.interrupt_banner import InterruptBanner
from mind.ui.terminal_tab import TerminalScreenWidget, WorkerTabBar, WorkerTerminalTab


class WorkspaceScreen(Screen):
    """Main workspace screen with split-pane agent views, visible tab bar, and Vim modal system.

    Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │ HeaderBar: [mind] | [session] | [mode] | [mcp] | [workers]  │
    ├─────────────────────────────────────────────────────────────┤
    │ InterruptBanner (hidden until triggered)                    │
    ├──────────────────────────────┬──────────────────────────────┤
    │ Primary Agent Pane           │ [1:Worker-1 (agy)] [+New(c)] │
    │ (left / coordinator stream)  │ Active Terminal Viewport     │
    │                              │ (right / interactive PTY)    │
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
        ("ctrl+b", "enter_normal", "Normal Mode"),
        ("f12", "enter_normal", "Normal Mode"),
        ("ctrl+shift+c", "copy_to_clipboard", "Copy"),
        ("y", "copy_to_clipboard", "Yank / Copy"),
        ("m", "open_directive_modal", "Inject Directive"),
        ("ctrl+m", "open_directive_modal", "Inject Directive"),
        ("o", "open_directive_external", "Open Directive File"),
        ("ctrl+o", "open_directive_external", "Open Directive File"),
        ("d", "open_directive_editor", "Edit Directive In-App"),
        ("ctrl+d", "open_directive_editor", "Edit Directive In-App"),
        ("e", "open_agent_config_modal", "Configure Agent"),
        ("ctrl+e", "open_agent_config_modal", "Configure Agent"),
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
        working_dir: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._session_name = session_name
        self._agent_count = max(agent_count, 1)
        self._goal = goal
        self._working_dir = working_dir or TerminalManager.get_launch_cwd() or os.path.abspath(os.getcwd())
        TerminalManager.set_launch_cwd(self._working_dir)
        self._agents: list[AgentInfo] = []
        self._coordinator_tab: WorkerTerminalTab | None = None
        self._worker_tabs: dict[str, WorkerTerminalTab] = {}
        self._active_worker_id: str = "1"
        self._is_split_view: bool = True
        self._terminal_manager = TerminalManager.get_instance()

    @property
    def session_name(self) -> str:
        """Name of the active multi-agent session."""
        return self._session_name

    @property
    def agent_count(self) -> int:
        """Configured number of agents in this session."""
        return self._agent_count

    def _resolve_coordinator_command(self) -> list[str]:
        """Resolve command line to launch agy as Primary Coordinator in a clean, idle state."""
        # 1. Prioritize direct agy executable to avoid nested cmd/python wrapper delays and lock contention
        agy_bin = shutil.which("agy") or shutil.which("agy.exe")
        if not agy_bin and sys.platform == "win32":
            local_agy = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
            if os.path.exists(local_agy):
                agy_bin = local_agy

        # 2. Fallback to agy1 launcher
        agy1_launcher = shutil.which("agy1") or shutil.which("agy1.cmd")
        if not agy1_launcher and sys.platform == "win32":
            local_agy1 = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy1.cmd")
            if os.path.exists(local_agy1):
                agy1_launcher = local_agy1

        target_bin = agy_bin or agy1_launcher
        if target_bin:
            # Primary Coordinator launches in a clean, idle interactive state without initial prompt
            return [target_bin, "--mode", "auto"]

        # 3. Fallback for test/offline environments
        if sys.platform == "win32":
            return ["powershell.exe", "-NoLogo"]
        return ["/bin/bash"]

    def compose(self) -> ComposeResult:
        self._agents = get_mock_agents(self._agent_count)
        worker_count = max(len(self._agents) - 1, 0)
        self._active_worker_id = str(self._agents[1].id) if len(self._agents) > 1 else "1"

        # 1. Streamlined Header Bar (dock: top, height: 1)
        yield HeaderBar(
            session_name=self._session_name,
            worker_count=worker_count,
            mode=self.mode,
        )

        # 2. Inter-agent interrupt banner (hidden until directive arrives)
        yield InterruptBanner()

        # 3. Main Workspace: Primary coordinator pane (left) + Worker PTYs (right)
        coordinator_cmd = self._resolve_coordinator_command()
        coordinator_task = self._goal or "Idle - Standing by for user prompt"
        coordinator_session = self._terminal_manager.create_worker(
            worker_id="coordinator",
            agent_id="coordinator",
            name="Primary-Coordinator",
            role="coordinator",
            assigned_agent="agy1",
            model="gemini-3.8-flash-high",
            task=coordinator_task,
            command=coordinator_cmd,
            cwd=self._working_dir,
            autostart=True,
        )
        self._coordinator_tab = WorkerTerminalTab(
            worker_session=coordinator_session,
            mode=self.mode,
            id="primary-pane",
        )
        self._coordinator_tab.styles.width = "1fr"

        with Horizontal(id="workspace-container"):
            yield self._coordinator_tab

            # Worker interactive PTY terminal viewport with visible Tab Bar
            if len(self._agents) > 1:
                workers_pane = Vertical(id="workers-pane")
                workers_pane.styles.width = "1fr"
                with workers_pane:
                    initial_worker_id = str(self._agents[1].id)

                    # Visible Tab Bar at top showing all active workers
                    yield WorkerTabBar(
                        active_worker_id=initial_worker_id,
                        workers=[(str(a.id), a.name) for a in self._agents[1:]],
                        id="worker-tab-bar",
                    )

                    # ContentSwitcher holding the active interactive terminal view
                    with ContentSwitcher(id="worker-switcher", initial=f"worker-view-{initial_worker_id}"):
                        for agent in self._agents[1:]:
                            worker_id = str(agent.id)
                            # Start only the active worker at boot; others spawn lazily upon activation
                            is_initial = (worker_id == initial_worker_id)
                            session = self._terminal_manager.create_worker(
                                worker_id=worker_id,
                                name=agent.name,
                                model=agent.model,
                                task=agent.task,
                                assigned_agent=f"agy{int(worker_id) + 1}" if worker_id.isdigit() else "",
                                cwd=self._working_dir,
                                autostart=is_initial,
                            )
                            tab_widget = WorkerTerminalTab(
                                worker_session=session,
                                mode=self.mode,
                                id=f"worker-view-{worker_id}",
                            )
                            self._worker_tabs[worker_id] = tab_widget
                            yield tab_widget

        # 4. Interactive Bottom Status Bar (dock: bottom, height: 1)
        yield BottomBar(worker_count=worker_count, mode=self.mode)

    def on_mount(self) -> None:
        """Initialize background MCP server, notification listeners, and auto-focus active terminal."""
        start_background_mcp_server(host="127.0.0.1", port=8765)
        self._terminal_manager.add_notification_listener(self._on_mcp_directive_injected)
        self._terminal_manager.add_alarm_listener(self._on_coordinator_alarm_received)
        self._terminal_manager.add_directive_listener(self._on_directive_reloaded)
        self.set_timer(0.05, self._auto_focus_terminal)

    def on_unmount(self) -> None:
        """Cleanup listeners when workspace unmounts."""
        try:
            self._terminal_manager.remove_directive_listener(self._on_directive_reloaded)
        except Exception:
            pass

    def _on_directive_reloaded(self, target: str, content: str, updated_workers: list[Any]) -> None:
        """Handle directive hot-reload notification."""
        count = len(updated_workers)
        msg = f"Directive hot-reloaded: {target}"
        if count:
            msg += f" (applied to {count} session{'s' if count > 1 else ''})"
        self._safe_notify(msg, title="Directives Hot-Reload", severity="information", timeout=3.0)

    def _on_coordinator_alarm_received(self, event: dict[str, Any]) -> None:
        """Handle event-driven wake-up alarms from worker terminals."""
        event_type = event.get("type", "worker_idle")
        worker_id = event.get("worker_id", "")
        summary = event.get("summary") or event.get("reason") or "Worker event received"
        badge = event.get("badge") or (
            f"Worker-{worker_id} Finished (Idle)"
            if event_type == "worker_idle"
            else "Assistance Needed"
        )

        # 1. Update Coordinator pane header badge subtly
        coord_tab = getattr(self, "_coordinator_tab", None)
        if not coord_tab:
            try:
                coord_tab = self.query_one("#primary-pane", WorkerTerminalTab)
            except Exception:
                coord_tab = None

        if coord_tab:
            coord_tab.set_alarm_badge(badge)

        # 2. Only show toast if user explicitly requests help, preventing repetitive idle toast spam
        if event_type != "worker_idle":
            self._safe_notify(f"{badge}: {summary}", severity="warning", timeout=3.0)

        # 3. For critical assistance requests only, forward a directive to Coordinator PTY.
        # Routine idle transitions are logged in MCP check_coordinator_alarms() to prevent Echo Loop flood.
        coord_session = self._terminal_manager.get_worker("coordinator")
        if coord_session and coord_session.is_alive and event_type != "worker_idle":
            priority = event.get("priority", "high")
            status_line = (
                f"\n[Assistance Needed from Worker-{worker_id} | Priority: {priority.upper()}]: {summary}\n"
                f"Coordinator Directive: Intervene to resolve roadblock.\n"
            )
            coord_session.write(status_line, press_enter=True)

    def on_unmount(self) -> None:
        """Clean up background tasks on unmount."""
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

        coord_tab = getattr(self, "_coordinator_tab", None)
        if not coord_tab:
            try:
                coord_tab = self.query_one("#primary-pane", WorkerTerminalTab)
            except Exception:
                coord_tab = None

        if coord_tab and coord_tab.screen_widget:
            coord_tab.screen_widget.mode = new_mode
            coord_tab.screen_widget.refresh()

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
        self._safe_notify("PTY Mode Active (Press Esc Esc or Ctrl+B for Outer Normal)", timeout=1.5)

    def action_enter_normal(self) -> None:
        """Switch to NORMAL (Vim Command) mode."""
        self.mode = "NORMAL"
        self._auto_focus_terminal()
        self._safe_notify("Normal Mode Active (Press 'i' to type in agy)", timeout=1.5)

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

    @on(TerminalScreenWidget.OpenDirectiveFileRequested)
    def on_open_directive_file_requested(self, event: TerminalScreenWidget.OpenDirectiveFileRequested) -> None:
        """Handle opening directive in external editor triggered while in PTY mode."""
        self.action_open_directive_external()

    @on(TerminalScreenWidget.OpenDirectiveEditorRequested)
    def on_open_directive_editor_requested(self, event: TerminalScreenWidget.OpenDirectiveEditorRequested) -> None:
        """Handle opening in-app directive editor modal triggered while in PTY mode."""
        self.action_open_directive_editor()

    @on(TerminalScreenWidget.OpenConfigRequested)
    def on_open_config_requested(self, event: TerminalScreenWidget.OpenConfigRequested) -> None:
        """Handle agent config modal request triggered while in PTY mode."""
        self.action_open_agent_config_modal()

    def _auto_focus_terminal(self) -> None:
        """Focus the currently active terminal screen."""
        coord_tab = getattr(self, "_coordinator_tab", None)
        coord_screen = coord_tab.screen_widget if coord_tab else None
        if coord_screen and self.focused == coord_screen:
            try:
                coord_screen.focus()
            except Exception:
                pass
            return

        tab_widget = self._worker_tabs.get(str(self._active_worker_id))
        if tab_widget and tab_widget.screen_widget:
            try:
                tab_widget.screen_widget.focus()
            except Exception:
                pass
            return

        if coord_screen:
            try:
                coord_screen.focus()
            except Exception:
                pass
            return

        # Fallback to first available worker screen
        for tab in self._worker_tabs.values():
            if tab.screen_widget:
                try:
                    tab.screen_widget.focus()
                except Exception:
                    pass
                break

    # ── Vim Modal Key Interception ─────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        """Intercept single-key commands in NORMAL mode and prevent leaking to subprocess."""
        # 0. Global Clipboard Copy: Ctrl+Shift+C in both modes
        key = event.key.lower()
        char = (event.character or "").lower()

        if key in ("ctrl+shift+c", "ctrl+shift+insert"):
            self.action_copy_to_clipboard()
            event.stop()
            event.prevent_default()
            return

        # If in PTY_INTERACT mode, only the dedicated Leader/Passthrough sequence leaves Insert mode
        if self.mode in ("PTY_INTERACT", "PTY"):
            if key in ("ctrl+b", "f12", "ctrl+right_square_bracket", "ctrl+]"):
                self.action_enter_normal()
                event.stop()
                event.prevent_default()
                return

            if key in ("escape", "caps_lock"):
                now = time.time()
                last_esc = getattr(self, "_last_outer_esc_time", 0.0)
                if last_esc and (now - last_esc <= 0.35):
                    self._last_outer_esc_time = 0.0
                    self.action_enter_normal()
                else:
                    self._last_outer_esc_time = now
                event.stop()
                event.prevent_default()
                return

            # In PTY_INTERACT mode, do NOT intercept single navigation keys
            return

        # ── NORMAL MODE COMMAND INTERCEPTION ──
        # Clipboard Yank: 'y' in NORMAL mode
        if key == "y" or char == "y":
            self.action_copy_to_clipboard()
            event.stop()
            event.prevent_default()
            return

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

        # 5. 'm': Open Agent Assignment & Task Dispatcher Modal
        if key == "m" or char == "m":
            self.action_open_directive_modal()
            event.stop()
            event.prevent_default()
            return

        # 6. 'e': Open Agent Configuration & CLI Tuning Modal
        if key == "e" or char == "e":
            self.action_open_agent_config_modal()
            event.stop()
            event.prevent_default()
            return

        # 7. 's': Toggle between Split View and Full-Screen Active Worker
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

        # 11. 'd': Open In-App Directive Modal Editor
        if key == "d" or char == "d":
            self.action_open_directive_editor()
            event.stop()
            event.prevent_default()
            return

        # 12. 'o': Open Directive File in External Editor
        if key == "o" or char == "o":
            self.action_open_directive_external()
            event.stop()
            event.prevent_default()
            return

        # 13. 'tab': Cycle focus between Primary Agent pane and Worker Terminal
        if key == "tab":
            self.action_focus_next()
            event.stop()
            event.prevent_default()
            return

        # Prevent unmapped keys from leaking in NORMAL mode
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

    # ── Workspace Actions ──────────────────────────────────────────

    def action_copy_to_clipboard(self) -> None:
        """Copy active selection or recent buffer of currently focused pane to system clipboard."""
        focused = self.focused
        if focused and hasattr(focused, "copy_selection_or_buffer"):
            text = focused.copy_selection_or_buffer()
            if text:
                return

        # Fallback to focused pane widget
        coord_tab = getattr(self, "_coordinator_tab", None)
        active_worker_tab = self._worker_tabs.get(str(self._active_worker_id))

        target_widget = None
        if coord_tab and (self.focused == coord_tab.screen_widget):
            target_widget = coord_tab.screen_widget
        elif active_worker_tab and active_worker_tab.screen_widget:
            target_widget = active_worker_tab.screen_widget
        elif coord_tab and coord_tab.screen_widget:
            target_widget = coord_tab.screen_widget

        if target_widget and hasattr(target_widget, "copy_selection_or_buffer"):
            target_widget.copy_selection_or_buffer()
        else:
            self._safe_notify("Nothing to copy to clipboard", severity="warning")

    def action_quit(self) -> None:
        """Exit the application and stop background processes."""
        self._terminal_manager.stop_all()
        stop_background_mcp_server()
        self.app.exit()

    def action_show_help(self) -> None:
        """Show the help modal dialog."""
        from mind.ui.help_modal import HelpModal

        self.app.push_screen(HelpModal())

    def _resolve_active_directive_target(self) -> str:
        """Resolve directive target ('coordinator', 'agy1', etc.) based on currently focused pane or tab."""
        coord_tab = getattr(self, "_coordinator_tab", None)
        if coord_tab and coord_tab.has_focus_within:
            return "coordinator"

        worker = self._terminal_manager.get_worker(str(self._active_worker_id))
        if worker and worker.assigned_agent:
            return worker.assigned_agent
        return f"agy{self._active_worker_id}"

    def action_open_directive_external(self) -> None:
        """Open the active agent's directive Markdown file in the system default editor."""
        target = self._resolve_active_directive_target()
        path = open_directive_in_editor(target)
        self._safe_notify(
            f"Opened Directive: {path.name}",
            title="External Editor",
            severity="information",
            timeout=3.0,
        )

    def action_open_directive_editor(self) -> None:
        """Open the in-app modal directive editor for the active agent."""
        target = self._resolve_active_directive_target()
        content = load_directive(target)
        self.app.push_screen(
            DirectiveEditorModal(target=target, current_content=content),
            callback=self._on_directive_editor_closed,
        )

    def _on_directive_editor_closed(self, result: str | None) -> None:
        """Callback when directive is saved or dismissed from DirectiveEditorModal."""
        if result is not None:
            target = self._resolve_active_directive_target()
            self._terminal_manager.apply_directive_update(target, result, source="modal")
            self._safe_notify(f"Directive saved for {target}", severity="information", timeout=2.5)

    def action_open_directive_modal(self) -> None:
        """Open Agent Assignment & Task Dispatcher modal."""
        self.app.push_screen(
            DirectiveModal(default_target=self._active_worker_id),
            callback=lambda _: self._on_directive_modal_closed(),
        )

    def _on_directive_modal_closed(self) -> None:
        """Record session activity upon directive modal closure."""
        try:
            record_session_activity(self.session_name, steps=1)
        except Exception:
            pass

    def action_open_agent_config_modal(self) -> None:
        """Open Agent Configuration & CLI Tuning modal."""
        self.app.push_screen(
            AgentConfigModal(
                default_target=self._active_worker_id,
                on_save_callback=self._on_worker_configured,
            )
        )

    def _on_worker_configured(self, worker_id: str, new_config: dict[str, Any], restarted: bool) -> None:
        """Callback when worker configuration is updated in AgentConfigModal."""
        new_name = new_config.get("name")
        if new_name:
            if str(worker_id) in ("coordinator", "primary"):
                if len(self._agents) > 0:
                    self._agents[0].name = new_name
                    if new_config.get("model"):
                        self._agents[0].model = new_config["model"]
                coord_tab = getattr(self, "_coordinator_tab", None)
                if coord_tab:
                    try:
                        coord_tab.update_header_info()
                    except Exception:
                        pass
                return

            # Update matching agent in self._agents
            for agent in self._agents:
                if str(agent.id) == str(worker_id):
                    agent.name = new_name
                    if new_config.get("model"):
                        agent.model = new_config["model"]
                    break

            # Rebuild tab bar
            try:
                tab_bar = self.query_one("#worker-tab-bar", WorkerTabBar)
                tab_bar.rebuild(
                    workers=[(str(a.id), a.name) for a in self._agents[1:]],
                    active_worker_id=self._active_worker_id,
                )
            except Exception:
                pass

            # Update WorkerTerminalTab header dynamically
            tab_widget = self._worker_tabs.get(str(worker_id))
            if tab_widget:
                try:
                    tab_widget.update_header_info()
                except Exception:
                    pass

    def action_interrupt_active(self) -> None:
        """Send immediate interrupt (SIGINT/Ctrl+C) to the currently selected worker."""
        worker = self._terminal_manager.get_worker(str(self._active_worker_id))
        if worker:
            worker.interrupt()
            self._safe_notify(f"Interrupted Worker-{self._active_worker_id}", severity="warning")
            return

        workers = self._terminal_manager.list_workers()
        if workers:
            workers[0].interrupt()
            self._safe_notify(f"Interrupted {workers[0].name}", severity="warning")

    def action_next_worker(self) -> None:
        """Switch to next worker tab ('l' in NORMAL mode)."""
        worker_ids = list(self._worker_tabs.keys()) if self._worker_tabs else [str(a.id) for a in self._agents[1:]]
        if not worker_ids:
            return
        idx = worker_ids.index(str(self._active_worker_id)) if str(self._active_worker_id) in worker_ids else -1
        next_id = worker_ids[(idx + 1) % len(worker_ids)]
        self.action_switch_worker(next_id)

    def action_prev_worker(self) -> None:
        """Switch to previous worker tab ('h' in NORMAL mode)."""
        worker_ids = list(self._worker_tabs.keys()) if self._worker_tabs else [str(a.id) for a in self._agents[1:]]
        if not worker_ids:
            return
        idx = worker_ids.index(str(self._active_worker_id)) if str(self._active_worker_id) in worker_ids else 0
        prev_id = worker_ids[(idx - 1) % len(worker_ids)]
        self.action_switch_worker(prev_id)

    def action_switch_worker(self, worker_id: str) -> None:
        """Switch active worker tab and focus its terminal (spawning PTY lazily if not started)."""
        worker_id_str = str(worker_id)
        if worker_id_str not in self._worker_tabs:
            try:
                idx = int(worker_id_str) - 1
                available_ids = list(self._worker_tabs.keys())
                if 0 <= idx < len(available_ids):
                    worker_id_str = available_ids[idx]
                else:
                    return
            except ValueError:
                return

        self._active_worker_id = worker_id_str

        # 0. Lazy spawn: ensure worker process starts when its tab is first activated
        target_session = self._terminal_manager.get_worker(worker_id_str)
        if target_session and not target_session.is_alive and target_session.process is None:
            target_session.start()

        # 1. Switch visible viewport via ContentSwitcher
        try:
            switcher = self.query_one("#worker-switcher", ContentSwitcher)
            switcher.current = f"worker-view-{worker_id_str}"
        except Exception:
            pass

        # 2. Update visible tab bar highlight
        try:
            tab_bar = self.query_one("#worker-tab-bar", WorkerTabBar)
            tab_bar.set_active(worker_id_str)
        except Exception:
            pass

        # 3. Focus active terminal screen widget and trigger immediate refresh
        tab_widget = self._worker_tabs.get(worker_id_str)
        if tab_widget and tab_widget.screen_widget:
            try:
                tab_widget.screen_widget.focus()
                tab_widget.screen_widget.refresh()
            except Exception:
                pass

    def action_close_active_tab(self) -> None:
        """Terminate and close active worker tab ('x' in NORMAL mode)."""
        if len(self._agents) <= 2:
            self._safe_notify("At least one worker agent tab must remain active.", severity="warning")
            return

        worker_id = str(self._active_worker_id)
        try:
            worker_session = self._terminal_manager.get_worker(worker_id)
            if worker_session:
                worker_session.terminate()

            tab_widget = self._worker_tabs.pop(worker_id, None)
            if tab_widget:
                tab_widget.remove()

            self._agents = [a for a in self._agents if str(a.id) != worker_id]

            # Update count in status bars
            remaining_count = max(len(self._agents) - 1, 0)
            try:
                self.query_one(HeaderBar).worker_count = remaining_count
                self.query_one(BottomBar).worker_count = remaining_count
            except Exception:
                pass

            # Activate first available remaining tab
            remaining_workers = [(str(a.id), a.name) for a in self._agents[1:]]
            if remaining_workers:
                next_id = remaining_workers[0][0]
                try:
                    tab_bar = self.query_one("#worker-tab-bar", WorkerTabBar)
                    tab_bar.rebuild(remaining_workers, active_worker_id=next_id)
                except Exception:
                    pass
                self.action_switch_worker(next_id)

            self._safe_notify(f"Closed worker tab {worker_id}", severity="information")
        except Exception as exc:
            self._safe_notify(f"Could not close worker tab: {exc}", severity="error")

    def action_focus_next(self) -> None:
        """Toggle focus between Primary Coordinator terminal and active worker terminal."""
        coord_tab = getattr(self, "_coordinator_tab", None)
        if not coord_tab:
            try:
                coord_tab = self.query_one("#primary-pane", WorkerTerminalTab)
            except Exception:
                coord_tab = None

        coord_screen = coord_tab.screen_widget if coord_tab else None

        active_worker_tab = self._worker_tabs.get(str(self._active_worker_id))
        worker_screen = active_worker_tab.screen_widget if active_worker_tab else None

        if not worker_screen:
            for tab in self._worker_tabs.values():
                if tab.screen_widget:
                    worker_screen = tab.screen_widget
                    break

        if not coord_screen and not worker_screen:
            try:
                self.focus_next()
            except Exception:
                pass
            return

        if not coord_screen:
            if worker_screen:
                worker_screen.focus()
            return

        if not worker_screen:
            coord_screen.focus()
            return

        # Check whether coordinator is currently focused (or has focus within)
        is_coord_focused = (self.focused == coord_screen) or (
            coord_tab is not None and coord_tab.has_focus
        )

        if is_coord_focused:
            worker_screen.focus()
            self._safe_notify("Focused: Active Worker Terminal", timeout=1.0)
        else:
            coord_screen.focus()
            self._safe_notify("Focused: Primary Coordinator", timeout=1.0)

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
            assigned_agent=f"agy{int(new_id) + 1}" if new_id.isdigit() else "",
            cwd=self._working_dir,
            autostart=True,
        )
        tab_widget = WorkerTerminalTab(
            worker_session=session,
            mode=self.mode,
            id=f"worker-view-{new_id}",
        )
        self._worker_tabs[new_id] = tab_widget

        try:
            switcher = self.query_one("#worker-switcher", ContentSwitcher)
            switcher.mount(tab_widget)
        except Exception:
            pass

        try:
            tab_bar = self.query_one("#worker-tab-bar", WorkerTabBar)
            tab_bar.rebuild(
                workers=[(str(a.id), a.name) for a in self._agents[1:]],
                active_worker_id=new_id,
            )
        except Exception:
            pass

        active_worker_count = len(self._agents) - 1
        try:
            self.query_one(HeaderBar).worker_count = active_worker_count
            self.query_one(BottomBar).worker_count = active_worker_count
        except Exception:
            pass

        self.action_switch_worker(new_id)
        self._safe_notify(f"Spawned {new_agent.name} with live PTY session.")

    def action_toggle_split(self) -> None:
        """Toggle between single-agent full-screen view and split-screen view ('s' in NORMAL mode)."""
        self._is_split_view = not self._is_split_view
        try:
            primary = self.query_one("#primary-pane")
            workers = self.query_one("#workers-pane")
            if self._is_split_view:
                primary.styles.display = "block"
                primary.styles.width = "1fr"
                workers.styles.display = "block"
                workers.styles.width = "1fr"
                self._safe_notify("Split View: Primary Coordinator + Active Worker")
            else:
                # Check whether coordinator pane was currently focused
                coord_tab = getattr(self, "_coordinator_tab", None)
                coord_screen = coord_tab.screen_widget if coord_tab else None
                is_coord_focused = (
                    self.focused is not None
                    and (self.focused == coord_screen or (coord_tab is not None and coord_tab.has_focus))
                )
                if is_coord_focused:
                    workers.styles.display = "none"
                    primary.styles.display = "block"
                    primary.styles.width = "100%"
                    self._safe_notify("Full Screen View: Primary Coordinator Only (Press 's' for Split)")
                else:
                    primary.styles.display = "none"
                    workers.styles.display = "block"
                    workers.styles.width = "100%"
                    self._safe_notify("Full Screen View: Active Worker Only (Press 's' for Split)")
            self._auto_focus_terminal()
        except Exception:
            pass

    def action_go_back(self) -> None:
        """Return to session picker screen."""
        stop_background_mcp_server()
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()
