"""Unit tests for Vim-like Modal System (Normal vs PTY_INTERACT modes)."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from textual.events import Key

from mind.core.terminal_manager import WorkerSession
from mind.ui.bottom_bar import BottomBar
from mind.ui.header_bar import HeaderBar
from mind.ui.terminal_tab import TerminalScreenWidget
from mind.ui.workspace import WorkspaceScreen


def _create_mock_worker_session(worker_id: str = "test-1") -> WorkerSession:
    """Create a mock WorkerSession."""
    session = WorkerSession(
        worker_id=worker_id,
        name=f"Worker-{worker_id}",
        model="gpt-4o-mini",
        task="Test task",
    )
    session.write = MagicMock()
    return session


def test_terminal_screen_widget_normal_mode_does_not_consume_keys() -> None:
    """In NORMAL mode, TerminalScreenWidget must not write to worker process and must not stop events."""
    session = _create_mock_worker_session()
    widget = TerminalScreenWidget(worker_session=session, mode="NORMAL")

    event = Key("i", character="i")
    widget.on_key(event)

    # Must NOT write to worker process
    session.write.assert_not_called()
    assert not event._stop_propagation
    assert not event._no_default_action


def test_terminal_screen_widget_pty_mode_writes_characters() -> None:
    """In PTY_INTERACT mode, raw keystrokes are passed directly to worker process."""
    session = _create_mock_worker_session()
    widget = TerminalScreenWidget(worker_session=session, mode="PTY_INTERACT")

    event = Key("a", character="a")
    widget.on_key(event)

    session.write.assert_called_once_with("a")
    assert event._stop_propagation
    assert event._no_default_action


def test_terminal_screen_widget_escape_leaves_pty_mode() -> None:
    """In PTY_INTERACT mode, double Escape (Esc Esc) emits ModeChangeRequested('NORMAL'),
    while single bare Escape passes through to child PTY, and Ctrl+B immediately escapes.
    """
    session = _create_mock_worker_session()
    widget = TerminalScreenWidget(worker_session=session, mode="PTY_INTERACT")

    posted_messages = []
    widget.post_message = lambda msg: posted_messages.append(msg)

    # 1. Single Escape: does NOT leave PTY mode immediately (buffered for passthrough)
    event1 = Key("escape", character="")
    widget.on_key(event1)
    assert len(posted_messages) == 0
    assert widget._pending_esc is True
    assert event1._stop_propagation

    # Timeout fires without 2nd escape -> writes bare '\x1b' directly to child PTY
    widget._on_esc_timeout()
    session.write.assert_called_once_with("\x1b")
    assert widget._pending_esc is False

    # 2. Double Escape (Esc Esc): leaves PTY mode
    session.write.reset_mock()
    event_esc1 = Key("escape", character="")
    widget.on_key(event_esc1)
    assert len(posted_messages) == 0

    event_esc2 = Key("escape", character="")
    widget.on_key(event_esc2)
    assert len(posted_messages) == 1
    assert isinstance(posted_messages[0], TerminalScreenWidget.ModeChangeRequested)
    assert posted_messages[0].target_mode == "NORMAL"
    session.write.assert_not_called()

    # 3. Dedicated Leader Key (Ctrl+B): leaves PTY mode immediately
    posted_messages.clear()
    event_ctrl_b = Key("ctrl+b", character="")
    widget.on_key(event_ctrl_b)
    assert len(posted_messages) == 1
    assert posted_messages[0].target_mode == "NORMAL"

    # 4. Raw Ctrl+C: writes \x03 for process SIGINT interruption, NOT intercepted by copy
    session.write.reset_mock()
    event_ctrl_c = Key("ctrl+c", character="")
    widget.on_key(event_ctrl_c)
    session.write.assert_called_once_with("\x03")


def test_terminal_screen_widget_ctrl_m_opens_directive() -> None:
    """In PTY_INTERACT mode, Ctrl+M emits OpenDirectiveRequested without writing to stdin."""
    session = _create_mock_worker_session()
    widget = TerminalScreenWidget(worker_session=session, mode="PTY_INTERACT")

    posted_messages = []
    widget.post_message = lambda msg: posted_messages.append(msg)

    event = Key("ctrl+m", character="")
    widget.on_key(event)

    session.write.assert_not_called()
    assert event._stop_propagation
    assert len(posted_messages) == 1
    assert isinstance(posted_messages[0], TerminalScreenWidget.OpenDirectiveRequested)


def test_terminal_screen_widget_ctrl_e_opens_config() -> None:
    """In PTY_INTERACT mode, Ctrl+E emits OpenConfigRequested without writing to stdin."""
    session = _create_mock_worker_session()
    widget = TerminalScreenWidget(worker_session=session, mode="PTY_INTERACT")

    posted_messages = []
    widget.post_message = lambda msg: posted_messages.append(msg)

    event = Key("ctrl+e", character="")
    widget.on_key(event)

    session.write.assert_not_called()
    assert event._stop_propagation
    assert len(posted_messages) == 1
    assert isinstance(posted_messages[0], TerminalScreenWidget.OpenConfigRequested)


def test_header_and_bottom_bar_mode_indicators() -> None:
    """HeaderBar is clean without redundant mode badges; BottomBar is single source of truth for mode indicator."""
    header = HeaderBar(session_name="test-session", worker_count=2, mode="NORMAL")
    bottom = BottomBar(worker_count=2, mode="NORMAL")

    # HeaderBar maintains clean telemetry without redundant mode badges
    assert header.session_name == "test-session"
    assert header.worker_count == 2
    assert header.mcp_port == 8765

    # BottomBar is the single source of truth for mode indicator
    assert "NORMAL MODE" in bottom._build_mode_indicator()
    assert "Press 'i' to type in agy" in bottom._build_mode_indicator()

    # In PTY_INTERACT mode
    bottom.mode = "PTY_INTERACT"
    assert "PTY INTERACT" in bottom._build_mode_indicator()
    assert "Press Esc Esc or Ctrl+B for Outer Normal" in bottom._build_mode_indicator()


def test_workspace_screen_vim_key_dispatch() -> None:
    """WorkspaceScreen intercepts single-key commands in NORMAL mode."""
    ws = WorkspaceScreen(session_name="test-vim", agent_count=3)
    assert ws.mode == "NORMAL"

    # Mock actions
    ws.action_enter_pty = MagicMock()
    ws.action_prev_worker = MagicMock()
    ws.action_next_worker = MagicMock()
    ws.action_open_directive_modal = MagicMock()
    ws.action_open_agent_config_modal = MagicMock()
    ws.action_toggle_split = MagicMock()
    ws.action_new_tab = MagicMock()
    ws.action_close_active_tab = MagicMock()
    ws.action_show_help = MagicMock()
    ws.action_quit = MagicMock()
    ws.action_switch_worker = MagicMock()
    ws.action_copy_to_clipboard = MagicMock()

    # 'y' -> yank to clipboard in NORMAL mode
    event_y = Key("y", character="y")
    ws.on_key(event_y)
    ws.action_copy_to_clipboard.assert_called_once()
    assert event_y._stop_propagation

    # 'i' -> enter PTY
    event_i = Key("i", character="i")
    ws.on_key(event_i)
    ws.action_enter_pty.assert_called_once()
    assert event_i._stop_propagation

    # 'h' -> previous worker
    event_h = Key("h", character="h")
    ws.on_key(event_h)
    ws.action_prev_worker.assert_called_once()
    assert event_h._stop_propagation

    # 'l' -> next worker
    event_l = Key("l", character="l")
    ws.on_key(event_l)
    ws.action_next_worker.assert_called_once()
    assert event_l._stop_propagation

    # '2' -> jump to worker 2
    event_2 = Key("2", character="2")
    ws.on_key(event_2)
    ws.action_switch_worker.assert_called_once_with("2")
    assert event_2._stop_propagation

    # 'm' -> open directive modal
    event_m = Key("m", character="m")
    ws.on_key(event_m)
    ws.action_open_directive_modal.assert_called_once()
    assert event_m._stop_propagation

    # 'e' -> open agent config modal
    event_e = Key("e", character="e")
    ws.on_key(event_e)
    ws.action_open_agent_config_modal.assert_called_once()
    assert event_e._stop_propagation

    # 's' -> toggle split
    event_s = Key("s", character="s")
    ws.on_key(event_s)
    ws.action_toggle_split.assert_called_once()
    assert event_s._stop_propagation

    # 'c' -> new tab
    event_c = Key("c", character="c")
    ws.on_key(event_c)
    ws.action_new_tab.assert_called_once()
    assert event_c._stop_propagation

    # 'x' -> close active tab
    event_x = Key("x", character="x")
    ws.on_key(event_x)
    ws.action_close_active_tab.assert_called_once()
    assert event_x._stop_propagation

    # '?' -> show help
    event_help = Key("question_mark", character="?")
    ws.on_key(event_help)
    ws.action_show_help.assert_called_once()
    assert event_help._stop_propagation

    # 'q' -> quit
    event_q = Key("q", character="q")
    ws.on_key(event_q)
    ws.action_quit.assert_called_once()
    assert event_q._stop_propagation


def test_action_new_tab_execution() -> None:
    """action_new_tab creates an agent with AgentStatus.RUNNING and does not raise AttributeError."""
    from mind.state.mock_data import get_mock_agents

    ws = WorkspaceScreen(session_name="test-session", agent_count=2)
    ws._agents = get_mock_agents(2)
    initial_count = len(ws._agents)

    # Calling action_new_tab directly
    ws.action_new_tab()
    assert len(ws._agents) == initial_count + 1
    new_agent = ws._agents[-1]
    assert new_agent.name == f"Worker-{new_agent.id}"
    assert new_agent.status.value == "running"


def test_worker_tab_bar_pills_and_split_toggle() -> None:
    """WorkerTabBar displays active tab pills and split-screen toggles properly."""
    from mind.ui.terminal_tab import WorkerTabBar, WorkerTabPill

    tab_bar = WorkerTabBar(active_worker_id="1", workers=[("1", "Worker-1"), ("2", "Worker-2")])
    assert tab_bar.active_worker_id == "1"
    assert len(tab_bar.tab_items) == 2

    # Workspace split toggle
    ws = WorkspaceScreen(session_name="test-split", agent_count=3)
    assert ws._is_split_view is True
    ws.action_toggle_split()
    assert ws._is_split_view is False
    ws.action_toggle_split()
    assert ws._is_split_view is True


def test_directive_modal_agent_assignment() -> None:
    """DirectiveModal enables selecting Primary or Worker agents, assigning roles, and dispatching prompts."""
    from mind.core.terminal_manager import TerminalManager
    from mind.ui.directive_modal import DirectiveModal

    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("worker-dispatch-test", name="Worker-Dispatch", autostart=False)

    modal = DirectiveModal(default_target="worker-dispatch-test")
    assert modal is not None
    assert modal._default_target == "worker-dispatch-test"


@pytest.mark.anyio
async def test_bottom_bar_config_action_pills() -> None:
    """BottomBar exposes interactive [e Config] pill in normal mode and [Ctrl+E Config] in PTY mode."""
    from textual.app import App

    class TestApp(App):
        def compose(self):
            yield BottomBar(worker_count=2, mode="NORMAL")

    app = TestApp()
    async with app.run_test() as pilot:
        normal_box = app.query_one("#bottom-normal-actions")
        assert normal_box is not None
        assert normal_box.query_one("#pill-config") is not None

        pty_box = app.query_one("#bottom-pty-actions")
        assert pty_box is not None
        assert pty_box.query_one("#pill-pty-config") is not None


def test_agent_config_modal_save_without_restart() -> None:
    """AgentConfigModal updates worker session and profile without respawning process."""
    from mind.core.terminal_manager import TerminalManager
    from mind.ui.agent_config_modal import AgentConfigModal

    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker(
        "worker-cfg-1",
        name="Worker-Original",
        model="gemini-3.8-flash-high",
        cli_mode="auto",
        reasoning_effort="high",
        autostart=False,
    )

    modal = AgentConfigModal(default_target="worker-cfg-1")
    # Simulate saving new configuration directly
    new_config = {
        "name": "agy 1",
        "cli_mode": "accept-edits",
        "model": "claude-sonnet-4-6",
        "reasoning_effort": "xhigh",
        "extra_flags": "--dangerously-skip-permissions --sandbox",
        "instructions": "Focus on high-speed refactoring",
    }

    # Update worker without restart
    worker.name = new_config["name"]
    worker.cli_mode = new_config["cli_mode"]
    worker.model = new_config["model"]
    worker.reasoning_effort = new_config["reasoning_effort"]
    worker.extra_flags = new_config["extra_flags"]
    worker.instructions = new_config["instructions"]
    worker.profile.cli_mode = new_config["cli_mode"]
    worker.profile.model = new_config["model"]
    worker.profile.reasoning_effort = new_config["reasoning_effort"]
    worker.profile.extra_flags = new_config["extra_flags"]
    worker.profile.instructions = new_config["instructions"]

    profile = worker.get_profile_dict()
    assert profile["name"] == "agy 1"
    assert profile["cli_mode"] == "accept-edits"
    assert profile["model"] == "claude-sonnet-4-6"
    assert profile["reasoning_effort"] == "xhigh"
    assert profile["extra_flags"] == "--dangerously-skip-permissions --sandbox"
    assert profile["instructions"] == "Focus on high-speed refactoring"


def test_agent_config_modal_save_and_restart() -> None:
    """TerminalManager.restart_worker respawns worker with new CLI config and resets buffer."""
    from mind.core.terminal_manager import TerminalManager

    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("worker-restart-test", name="Worker-PreRestart", autostart=False)
    worker.buffer.feed("Old terminal output buffer")
    assert any(line.strip() for line in worker.buffer.get_visible_lines())

    new_cfg = {
        "name": "Worker-PostRestart",
        "cli_mode": "plan",
        "model": "claude-opus-4-6-thinking",
        "reasoning_effort": "max",
        "extra_flags": "--sandbox --project test-proj",
        "instructions": "Plan all system architectures carefully",
    }

    # Test restart_worker with new_args as 2nd positional argument
    restarted = mgr.restart_worker("worker-restart-test", new_cfg)
    assert restarted is not None
    assert restarted.name == "Worker-PostRestart"
    assert restarted.cli_mode == "plan"
    assert restarted.model == "claude-opus-4-6-thinking"
    assert restarted.reasoning_effort == "max"
    assert restarted.extra_flags == "--sandbox --project test-proj"
    assert "--sandbox" in restarted.custom_cli_args
    assert "--project" in restarted.custom_cli_args
    assert "test-proj" in restarted.custom_cli_args

    profile = restarted.get_profile_dict()
    assert profile["custom_cli_args"] == ["--sandbox", "--project", "test-proj"]
    assert profile["behavioral_flags"] == ["--sandbox", "--project", "test-proj"]

    # Virtual buffer must be reset/cleared
    assert not any(line.strip() for line in restarted.buffer.get_visible_lines())


def test_dynamic_agent_discovery() -> None:
    """discover_system_agents discovers host-installed agents (agy1, agy2, etc.)."""
    from mind.core.agent_discovery import discover_system_agents, get_agent_preset_config

    agents = discover_system_agents()
    assert isinstance(agents, list)
    assert len(agents) >= 2
    assert "agy1" in agents
    assert "agy2" in agents

    preset = get_agent_preset_config("agy1")
    assert preset["alias"] == "agy1"
    assert "--agent agy1" in preset["extra_flags"]


def test_worker_tab_title_formatting_and_unicode() -> None:
    """WorkerTabBar formats clean tab labels without text clipping, supporting full Unicode."""
    from mind.ui.terminal_tab import WorkerTabBar

    # Default name
    t1 = WorkerTabBar._format_tab_title("1", "Worker-1", is_active=True)
    assert "[1] agy1 (Worker-1)" in t1

    # Custom alias
    t2 = WorkerTabBar._format_tab_title("2", "agy2", is_active=False)
    assert "[2] agy2 (Worker-2)" in t2

    # Unicode / non-ASCII name
    t3 = WorkerTabBar._format_tab_title("3", "مطور", is_active=False)
    assert "[3] مطور · Worker-3" in t3


def test_worker_terminal_header_instance_and_warning() -> None:
    """WorkerTerminalTab header explicitly renders active instance identifier and CLI warning badges."""
    from mind.core.terminal_manager import WorkerSession
    from mind.ui.terminal_tab import WorkerTerminalTab

    session = WorkerSession(
        worker_id="1",
        name="agy1",
        assigned_agent="agy1",
        model="gemini-3.8-flash-high",
        task="System tasks",
    )
    tab = WorkerTerminalTab(worker_session=session)

    header_text = tab._build_header_text()
    assert "● Worker-1" in header_text
    assert "Instance:" in header_text
    assert "agy1" in header_text

    # Feed a runtime warning into the worker process output
    session._on_process_output("Warning: --effort fallback to high\r\n")
    assert len(session.runtime_warnings) > 0
    header_with_warning = tab._build_header_text()
    assert "Warning: --effort fallback" in header_with_warning


def test_agent_config_modal_discovered_agents() -> None:
    """AgentConfigModal populates discovered system agents and pre-fills --agent flag."""
    from mind.ui.agent_config_modal import AgentConfigModal

    modal = AgentConfigModal(default_target="1")
    assert len(modal._discovered_agents) >= 2
    assert "agy1" in modal._discovered_agents


def test_coordinator_command_resolution_and_prompt() -> None:
    """WorkspaceScreen resolves agy in clean idle state without initial prompt."""
    from mind.ui.workspace import WorkspaceScreen

    ws = WorkspaceScreen(session_name="test-coord", agent_count=2, goal="Build payment API")
    cmd = ws._resolve_coordinator_command()
    assert isinstance(cmd, list)
    assert len(cmd) >= 3

    # Must include mode auto and NO initial interactive prompt
    assert "--mode" in cmd
    assert "auto" in cmd
    assert "--prompt-interactive" not in cmd
    assert "--prompt" not in cmd


@pytest.mark.anyio
async def test_coordinator_and_workers_open_on_same_launch_path(tmp_path: Path) -> None:
    """Coordinator and all worker agents open on the exact launch path of mind."""
    import os
    from pathlib import Path
    from textual.app import App
    from mind.core.terminal_manager import TerminalManager
    from mind.ui.workspace import WorkspaceScreen

    TerminalManager.reset()
    project_dir = str(tmp_path / "target_project")
    os.makedirs(project_dir, exist_ok=True)

    TerminalManager.set_launch_cwd(project_dir)
    assert TerminalManager.get_launch_cwd() == str(Path(project_dir).resolve())

    class TestPathApp(App):
        def on_mount(self) -> None:
            self.push_screen(WorkspaceScreen(session_name="test-path", agent_count=3, working_dir=project_dir))

    app = TestPathApp()
    async with app.run_test() as pilot:
        ws = app.screen
        assert isinstance(ws, WorkspaceScreen)
        assert ws._working_dir == str(Path(project_dir).resolve())

        # Verify coordinator session cwd
        coord = ws._terminal_manager.get_worker("coordinator")
        assert coord is not None
        assert coord.last_cwd == str(Path(project_dir).resolve())

        # Verify worker session cwd
        worker = ws._terminal_manager.get_worker("1")
        assert worker is not None
        assert worker.last_cwd == str(Path(project_dir).resolve())


@pytest.mark.anyio
async def test_primary_pane_coordinator_mounting_and_header() -> None:
    """WorkspaceScreen mounts #primary-pane as WorkerTerminalTab with Coordinator role and badges."""
    from textual.app import App
    from mind.core.terminal_manager import TerminalManager
    from mind.ui.terminal_tab import WorkerTerminalTab
    from mind.ui.workspace import WorkspaceScreen

    TerminalManager.reset()

    class TestApp(App):
        def on_mount(self) -> None:
            self.push_screen(WorkspaceScreen(session_name="test-coord-mount", agent_count=3))

    app = TestApp()
    async with app.run_test() as pilot:
        ws = app.screen
        assert isinstance(ws, WorkspaceScreen)
        primary_tab = ws._coordinator_tab
        assert primary_tab is not None
        assert isinstance(primary_tab, WorkerTerminalTab)
        assert primary_tab.id == "primary-pane"
        assert primary_tab.worker_session.role == "coordinator"
        assert primary_tab.worker_session.assigned_agent == "agy1"

        # Header text must render the Primary Coordinator badge
        header_text = primary_tab._build_header_text()
        assert "PRIMARY COORDINATOR" in header_text
        assert "agy1" in header_text


@pytest.mark.anyio
async def test_tab_focus_switching_between_coordinator_and_worker() -> None:
    """action_focus_next toggles focus between Primary Coordinator and active Worker."""
    from textual.app import App
    from mind.core.terminal_manager import TerminalManager
    from mind.ui.workspace import WorkspaceScreen

    TerminalManager.reset()

    class TestApp(App):
        def on_mount(self) -> None:
            self.push_screen(WorkspaceScreen(session_name="test-focus", agent_count=3))

    app = TestApp()
    async with app.run_test() as pilot:
        ws = app.screen
        assert isinstance(ws, WorkspaceScreen)

        coord_screen = ws._coordinator_tab.screen_widget
        active_worker = ws._worker_tabs.get("1")
        assert active_worker is not None
        worker_screen = active_worker.screen_widget

        # Focus coordinator screen first
        coord_screen.focus()
        await pilot.pause()
        assert ws.focused == coord_screen

        # Action focus next -> switches focus to worker
        ws.action_focus_next()
        await pilot.pause()
        assert ws.focused == worker_screen

        # Action focus next again -> switches focus back to coordinator
        ws.action_focus_next()
        await pilot.pause()
        assert ws.focused == coord_screen


def test_clipboard_copy_helper() -> None:
    """copy_to_clipboard and get_clipboard_text work safely with system clipboard."""
    from mind.ui.clipboard import copy_to_clipboard, get_clipboard_text

    test_content = "mind clipboard integration test string"
    success = copy_to_clipboard(test_content)
    assert success is True

    pasted = get_clipboard_text()
    assert test_content in pasted


def test_terminal_screen_mouse_selection_and_right_click_copy() -> None:
    """TerminalScreenWidget supports mouse drag selection, right-click copy, and auto-copy on mouse up."""
    from textual.events import MouseDown, MouseMove, MouseUp
    from mind.core.terminal_manager import WorkerSession
    from mind.ui.terminal_tab import TerminalScreenWidget

    session = _create_mock_worker_session()
    # Populate buffer with known lines
    session.buffer.feed("Hello World from Terminal\r\nLine 2 text here\r\n")

    widget = TerminalScreenWidget(worker_session=session, mode="NORMAL")

    # 1. Simulate mouse down at (0, 0)
    down_event = MouseDown(widget, 0, 0, 0, 0, button=1, shift=False, meta=False, ctrl=False)
    widget.on_mouse_down(down_event)
    assert widget._is_dragging is True
    assert widget._select_start == (0, 0)

    # 2. Simulate mouse drag to (11, 0) -> "Hello World"
    move_event = MouseMove(widget, 11, 0, 11, 0, button=1, shift=False, meta=False, ctrl=False)
    widget.on_mouse_move(move_event)
    assert widget.has_selection is True
    assert "Hello World" in widget.get_selected_text()

    # 3. Simulate mouse up with left click -> auto copies to clipboard
    up_event = MouseUp(widget, 11, 0, 11, 0, button=1, shift=False, meta=False, ctrl=False)
    widget.on_mouse_up(up_event)
    assert widget._is_dragging is False

    # 4. Right-click with active selection copies selected text and clears selection
    right_down = MouseDown(widget, 5, 0, 5, 0, button=3, shift=False, meta=False, ctrl=False)
    widget.on_mouse_down(right_down)
    assert widget.has_selection is False

    # 5. Right-click without selection copies visible buffer lines
    copied = widget.copy_selection_or_buffer()
    assert "Hello World" in copied


def test_agent_log_pane_clipboard_copy() -> None:
    """AgentLogPane copies color-formatted plain logs to system clipboard on right-click or y."""
    from datetime import datetime
    from textual.events import MouseUp
    from mind.state.models import AgentInfo, AgentRole, AgentStatus, LogEntry
    from mind.ui.agent_pane import AgentLogPane

    agent = AgentInfo(id=1, name="Worker-1", role=AgentRole.WORKER, status=AgentStatus.RUNNING, model="m", task="t")
    logs = [
        LogEntry(timestamp=datetime.now(), source="Worker-1", content="Task execution step 1", entry_type="info"),
        LogEntry(timestamp=datetime.now(), source="Worker-1", content="Evaluating file diff", entry_type="thought"),
    ]

    pane = AgentLogPane(agent=agent, logs=logs)
    copied = pane.copy_content()
    assert "Task execution step 1" in copied
    assert "Evaluating file diff" in copied

    # Mouse up with button 3 (right click) triggers copy_content
    right_up = MouseUp(pane, 10, 5, 10, 5, button=3, shift=False, meta=False, ctrl=False)
    pane.on_mouse_up(right_up)
    assert right_up._stop_propagation


def test_pty_interact_preserves_ctrl_c_and_allows_ctrl_shift_c_copy() -> None:
    """In PTY_INTERACT mode, raw Ctrl+C sends SIGINT (\x03) while Ctrl+Shift+C explicitly copies to clipboard."""
    session = _create_mock_worker_session()
    session.buffer.feed("Running long command output\r\n")
    widget = TerminalScreenWidget(worker_session=session, mode="PTY_INTERACT")

    # Ctrl+C must send \x03 to process
    event_ctrl_c = Key("ctrl+c", character="")
    widget.on_key(event_ctrl_c)
    session.write.assert_called_once_with("\x03")

    # Ctrl+Shift+C must call copy_selection_or_buffer and NOT write to worker stdin
    session.write.reset_mock()
    event_copy = Key("ctrl+shift+c", character="")
    widget.on_key(event_copy)
    session.write.assert_not_called()
    assert event_copy._stop_propagation


@pytest.mark.anyio
async def test_lazy_spawning_coordinator_and_first_worker_only() -> None:
    """Test that at boot only Coordinator and Worker-1 start; Worker-2 is lazily spawned on switch."""
    from textual.app import App
    from mind.core.terminal_manager import TerminalManager

    TerminalManager.reset()

    class TestApp(App):
        def on_mount(self) -> None:
            self.push_screen(WorkspaceScreen(session_name="test-lazy-mount", agent_count=3))

    app = TestApp()
    async with app.run_test() as pilot:
        ws = app.screen
        assert isinstance(ws, WorkspaceScreen)

        # 1. Coordinator session must have been created with autostart=True (process started)
        coord_tab = ws._coordinator_tab
        assert coord_tab is not None
        assert coord_tab.worker_session.process is not None
        assert coord_tab.worker_session.is_alive is True

        # 2. Worker 1 (initial active worker) must have been started
        worker1_tab = ws._worker_tabs.get("1")
        assert worker1_tab is not None
        assert worker1_tab.worker_session.process is not None
        assert worker1_tab.worker_session.is_alive is True

        # 3. Worker 2 (second worker) must NOT have been started yet (lazy standby)
        worker2_tab = ws._worker_tabs.get("2")
        assert worker2_tab is not None
        assert worker2_tab.worker_session.process is None
        assert worker2_tab.worker_session.is_alive is False

        # 4. Switching to Worker 2 triggers lazy spawn
        ws.action_switch_worker("2")
        await pilot.pause()
        assert ws._active_worker_id == "2"
        assert worker2_tab.worker_session.process is not None
        assert worker2_tab.worker_session.is_alive is True

        # 5. Switching back to Worker 1 and then to Worker 2 does not recreate process
        proc2 = worker2_tab.worker_session.process
        ws.action_switch_worker("1")
        await pilot.pause()
        ws.action_switch_worker("2")
        await pilot.pause()
        assert worker2_tab.worker_session.process is proc2


@pytest.mark.anyio
async def test_split_view_flexible_expansion_and_restore() -> None:
    """Test Split View layout: Coordinator on left, Worker on right, expandable to full screen."""
    from textual.app import App
    from mind.core.terminal_manager import TerminalManager

    TerminalManager.reset()

    class TestApp(App):
        def on_mount(self) -> None:
            self.push_screen(WorkspaceScreen(session_name="test-split-view", agent_count=3))

    app = TestApp()
    async with app.run_test() as pilot:
        ws = app.screen
        assert isinstance(ws, WorkspaceScreen)

        primary = ws.query_one("#primary-pane")
        workers = ws.query_one("#workers-pane")

        # Initial state: Split View (both visible with 1fr width)
        assert ws._is_split_view is True
        assert primary.styles.display == "block"
        assert primary.styles.width.value == 1
        assert workers.styles.display == "block"
        assert workers.styles.width.value == 1

        # Focus active worker pane first, then press 's' -> expands worker to full screen
        worker1_tab = ws._worker_tabs.get("1")
        assert worker1_tab is not None
        worker1_tab.screen_widget.focus()
        await pilot.pause()

        ws.action_toggle_split()
        await pilot.pause()
        assert ws._is_split_view is False
        assert primary.styles.display == "none"
        assert workers.styles.display == "block"
        assert workers.styles.width.value == 100

        # Press 's' again -> restores split view
        ws.action_toggle_split()
        await pilot.pause()
        assert ws._is_split_view is True
        assert primary.styles.display == "block"
        assert primary.styles.width.value == 1
        assert workers.styles.display == "block"
        assert workers.styles.width.value == 1

        # Focus coordinator pane, then press 's' -> expands coordinator to full screen
        ws._coordinator_tab.screen_widget.focus()
        await pilot.pause()
        ws.action_toggle_split()
        await pilot.pause()
        assert ws._is_split_view is False
        assert workers.styles.display == "none"
        assert primary.styles.display == "block"
        assert primary.styles.width.value == 100

        # Press 's' again -> restores split view
        ws.action_toggle_split()
        await pilot.pause()
        assert ws._is_split_view is True
        assert primary.styles.display == "block"
        assert primary.styles.width.value == 1
        assert workers.styles.display == "block"
        assert workers.styles.width.value == 1


def test_vim_modal_normal_key_isolation_and_navigation() -> None:
    """Test full single-key navigation suite in NORMAL mode and key leak isolation."""
    ws = WorkspaceScreen(session_name="test-modal-full", agent_count=3)
    ws.mode = "NORMAL"

    ws.action_enter_pty = MagicMock()
    ws.action_prev_worker = MagicMock()
    ws.action_next_worker = MagicMock()
    ws.action_open_directive_modal = MagicMock()
    ws.action_open_agent_config_modal = MagicMock()
    ws.action_toggle_split = MagicMock()
    ws.action_new_tab = MagicMock()
    ws.action_close_active_tab = MagicMock()
    ws.action_show_help = MagicMock()
    ws.action_quit = MagicMock()
    ws.action_switch_worker = MagicMock()
    ws.action_copy_to_clipboard = MagicMock()
    ws.action_open_directive_editor = MagicMock()
    ws.action_open_directive_external = MagicMock()

    # 1..9 jump
    for num in ("1", "3", "7", "9"):
        ev = Key(num, character=num)
        ws.on_key(ev)
        assert ev._stop_propagation
        assert ev._no_default_action
    assert ws.action_switch_worker.call_count == 4

    # h / l navigation
    ev_h = Key("h", character="h")
    ws.on_key(ev_h)
    ws.action_prev_worker.assert_called_once()
    assert ev_h._stop_propagation

    ev_l = Key("l", character="l")
    ws.on_key(ev_l)
    ws.action_next_worker.assert_called_once()
    assert ev_l._stop_propagation

    # s: split
    ev_s = Key("s", character="s")
    ws.on_key(ev_s)
    ws.action_toggle_split.assert_called_once()
    assert ev_s._stop_propagation

    # m: inject
    ev_m = Key("m", character="m")
    ws.on_key(ev_m)
    ws.action_open_directive_modal.assert_called_once()
    assert ev_m._stop_propagation

    # e: config
    ev_e = Key("e", character="e")
    ws.on_key(ev_e)
    ws.action_open_agent_config_modal.assert_called_once()
    assert ev_e._stop_propagation

    # c: new tab
    ev_c = Key("c", character="c")
    ws.on_key(ev_c)
    ws.action_new_tab.assert_called_once()
    assert ev_c._stop_propagation

    # x: close tab
    ev_x = Key("x", character="x")
    ws.on_key(ev_x)
    ws.action_close_active_tab.assert_called_once()
    assert ev_x._stop_propagation

    # y: copy / yank
    ev_y = Key("y", character="y")
    ws.on_key(ev_y)
    ws.action_copy_to_clipboard.assert_called_once()
    assert ev_y._stop_propagation

    # d: directive editor in-app
    ev_d = Key("d", character="d")
    ws.on_key(ev_d)
    ws.action_open_directive_editor.assert_called_once()
    assert ev_d._stop_propagation

    # o: directive editor external
    ev_o = Key("o", character="o")
    ws.on_key(ev_o)
    ws.action_open_directive_external.assert_called_once()
    assert ev_o._stop_propagation

    # Unmapped keys in NORMAL mode must be prevented from leaking
    ev_unmapped = Key("z", character="z")
    ws.on_key(ev_unmapped)
    assert ev_unmapped._stop_propagation
    assert ev_unmapped._no_default_action


def test_pty_interact_exit_keys_and_direct_passthrough() -> None:
    """In PTY_INTERACT mode: Ctrl+B, F12, and Esc Esc exit to NORMAL mode smoothly; inputs pass directly."""
    session = _create_mock_worker_session()
    widget = TerminalScreenWidget(worker_session=session, mode="PTY_INTERACT")

    posted_messages = []
    widget.post_message = lambda msg: posted_messages.append(msg)

    # 1. Ctrl+B exits immediately (0ms delay)
    ev_b = Key("ctrl+b", character="")
    widget.on_key(ev_b)
    assert len(posted_messages) == 1
    assert posted_messages[-1].target_mode == "NORMAL"
    assert ev_b._stop_propagation

    # 2. F12 exits immediately (0ms delay)
    posted_messages.clear()
    ev_f12 = Key("f12", character="")
    widget.on_key(ev_f12)
    assert len(posted_messages) == 1
    assert posted_messages[-1].target_mode == "NORMAL"
    assert ev_f12._stop_propagation

    # 3. Esc Esc within 350ms exits smoothly
    posted_messages.clear()
    ev_esc1 = Key("escape", character="")
    widget.on_key(ev_esc1)
    assert len(posted_messages) == 0  # 1st escape buffered
    assert widget._pending_esc is True

    ev_esc2 = Key("escape", character="")
    widget.on_key(ev_esc2)
    assert len(posted_messages) == 1
    assert posted_messages[-1].target_mode == "NORMAL"
    assert widget._pending_esc is False

    # 4. Standard keystrokes forwarded directly without any lag
    session.write.reset_mock()
    ev_char = Key("g", character="g")
    widget.on_key(ev_char)
    session.write.assert_called_once_with("g")
    assert ev_char._stop_propagation







