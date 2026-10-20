"""Tests for passive idle start, externalized directives, and event-driven alarms."""

import os
from pathlib import Path
import pytest

from mind.core.directives import (
    ensure_default_directives,
    get_coordinator_directive_path,
    get_directives_dir,
    get_worker_directive_path,
    load_directive,
    resolve_directive_path,
    save_directive,
)
from mind.core.terminal_manager import TerminalManager, WorkerProcessState
from mind.mcp.server import create_mcp_server
from mind.state.mock_data import get_mock_agents
from mind.ui.agent_config_modal import AgentConfigModal
from mind.ui.terminal_tab import WorkerTerminalTab
from mind.ui.workspace import WorkspaceScreen


def test_directives_file_persistence_and_resolution(tmp_path: Path, monkeypatch) -> None:
    """Directives are stored in predictable path and persist cleanly."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    ensure_default_directives()

    coord_path = get_coordinator_directive_path()
    assert coord_path.exists()
    content = coord_path.read_text(encoding="utf-8")
    assert "Primary Coordinator" in content

    worker_1_path = get_worker_directive_path("agy1")
    assert worker_1_path.exists()
    w_content = worker_1_path.read_text(encoding="utf-8")
    assert "Worker Agent Directive (agy1)" in w_content

    # Path resolution
    assert resolve_directive_path("coordinator") == coord_path
    assert resolve_directive_path("primary") == coord_path
    assert resolve_directive_path("agy2") == get_worker_directive_path("agy2")
    assert resolve_directive_path("3") == get_worker_directive_path("agy3")

    # Save and reload
    save_directive("agy2", "# Custom Rules\nAlways double check unit tests.")
    loaded = load_directive("agy2")
    assert "Always double check unit tests" in loaded


def test_passive_idle_startup(tmp_path: Path, monkeypatch) -> None:
    """mind starts in clean idle state without auto-prompts or unsolicited tasks."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    ws = WorkspaceScreen(session_name="test-idle-session", agent_count=3, goal="")
    cmd = ws._resolve_coordinator_command()

    # Must NOT inject automatic interactive prompt
    assert "--prompt-interactive" not in cmd
    assert "--prompt" not in cmd

    # Agents must start in IDLE state without unsolicited refactor tasks
    agents = get_mock_agents(3)
    assert agents[0].task.lower().startswith("idle")
    assert "refactor authentication module" not in agents[0].task.lower()
    for a in agents[1:]:
        assert a.task.lower().startswith("idle")
        assert a.status.value == "idle"


def test_event_driven_coordinator_alarms(tmp_path: Path, monkeypatch) -> None:
    """Event-driven wake-up alarms notify coordinator when worker completes or needs help."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    mgr = TerminalManager.get_instance()
    mgr.clear_coordinator_alarms()

    received_events = []
    mgr.add_alarm_listener(lambda ev: received_events.append(ev))

    # 1. Worker idle trigger
    event = mgr.notify_coordinator_worker_idle("2", "Worker-2 finished linting")
    assert event["type"] == "worker_idle"
    assert event["worker_id"] == "2"
    assert len(received_events) == 1

    # 2. Worker assistance trigger
    help_event = mgr.notify_coordinator_worker_help("3", "Missing dependencies", priority="critical")
    assert help_event["type"] == "worker_help"
    assert help_event["priority"] == "critical"
    assert len(received_events) == 2

    # 3. Verify MCP tools
    server = create_mcp_server(mgr)
    # Check alarms
    alarms = mgr.get_coordinator_alarms()
    assert len(alarms) == 2


def test_coordinator_pane_alarm_badge() -> None:
    """WorkerTerminalTab displays visual alarm badge when coordinator trigger fires."""
    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("coordinator", role="coordinator", autostart=False)
    tab = WorkerTerminalTab(worker_session=worker)

    tab.set_alarm_badge("⚡ Worker-1 Finished (Idle)")
    header = tab._build_header_text()
    assert "⚡ Worker-1 Finished (Idle)" in header

    tab.clear_alarm_badge()
    header_cleared = tab._build_header_text()
    assert "⚡ Worker-1 Finished (Idle)" not in header_cleared


def test_agent_config_modal_directive_editing(tmp_path: Path, monkeypatch) -> None:
    """AgentConfigModal reads, updates, and persists directives to disk in real time."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("worker-dir-test", assigned_agent="agy1", autostart=False)

    modal = AgentConfigModal(default_target="worker-dir-test")

    # Simulate in-app directive update callback
    modal._on_directive_edited("# Live Updated Rules\nReport metrics.")
    assert worker.instructions == "# Live Updated Rules\nReport metrics."
    assert worker.profile.instructions == "# Live Updated Rules\nReport metrics."

    # Verify persisted on disk
    loaded = load_directive("agy1")
    assert "Report metrics." in loaded
