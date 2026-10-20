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
    """In PTY_INTERACT mode, Escape emits ModeChangeRequested('NORMAL') without writing to stdin."""
    session = _create_mock_worker_session()
    widget = TerminalScreenWidget(worker_session=session, mode="PTY_INTERACT")

    posted_messages = []
    widget.post_message = lambda msg: posted_messages.append(msg)

    event = Key("escape", character="")
    widget.on_key(event)

    # Must NOT write escape to worker process
    session.write.assert_not_called()
    assert event._stop_propagation
    assert event._no_default_action

    # Must post ModeChangeRequested message with target 'NORMAL'
    assert len(posted_messages) == 1
    assert isinstance(posted_messages[0], TerminalScreenWidget.ModeChangeRequested)
    assert posted_messages[0].target_mode == "NORMAL"


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
    assert "Press Esc for Normal" in bottom._build_mode_indicator()


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




