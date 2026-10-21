"""Tests for passive idle start, externalized directives, and event-driven alarms."""

import os
from pathlib import Path
import pytest

from mind.core.alarm_pipeline import (
    CoordinatorAlarmPipeline,
    extract_status_summary,
    is_idle_prompt,
)
from mind.core.directives import (
    DirectivesWatcher,
    ensure_default_directives,
    extract_target_from_path,
    get_coordinator_directive_path,
    get_directives_dir,
    get_directives_watcher,
    get_worker_directive_path,
    load_directive,
    open_directive_in_editor,
    resolve_directive_path,
    save_directive,
    start_directives_watcher,
    stop_directives_watcher,
)
from mind.core.terminal_manager import TerminalManager, WorkerProcessState
from mind.mcp.server import create_mcp_server
from mind.state.mock_data import get_mock_agents
from mind.ui.agent_config_modal import AgentConfigModal
from mind.ui.directive_editor_modal import DirectiveEditorModal
from mind.ui.terminal_tab import TerminalScreenWidget, WorkerTerminalTab
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


def test_is_idle_prompt_detection() -> None:
    """Intelligent prompt detection matches interactive shell and CLI prompt endings."""
    # Positive prompt detections
    assert is_idle_prompt("PS C:\\Users\\test> ")
    assert is_idle_prompt("user@linux:~$ ")
    assert is_idle_prompt("mind> ")
    assert is_idle_prompt("agy> ")
    assert is_idle_prompt("❯ ")
    assert is_idle_prompt("Finished step.\n> ")
    assert is_idle_prompt("Would you like to proceed? (y/n) ")
    assert is_idle_prompt("? Select task to run: ")
    assert is_idle_prompt("\x1b[32muser@node\x1b[0m:\x1b[34m/app\x1b[0m$ ")

    # Negative non-prompt texts
    assert not is_idle_prompt("Compiling 45 source files...")
    assert not is_idle_prompt("Running pytest on module...")
    assert not is_idle_prompt("Executing task #8 without interruption")
    assert not is_idle_prompt("")


def test_extract_status_summary_from_worker_buffer() -> None:
    """Summary extraction pulls last meaningful output line before prompt."""
    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("extract-worker", autostart=False)

    worker.buffer.feed("Running build pipeline...\r\n")
    worker.buffer.feed("123 passed, 2 warnings in 58.82s\r\n")
    worker.buffer.feed("mind> ")

    summary = extract_status_summary(worker)
    assert "123 passed, 2 warnings" in summary
    assert "extract-worker" in summary


def test_single_thread_debounced_alarm_pipeline() -> None:
    """Pipeline operates via a single background thread and does not explode thread count."""
    import threading
    import time

    mgr = TerminalManager.get_instance()
    pipeline = mgr.alarm_pipeline
    assert pipeline is not None

    worker = mgr.create_worker("debounce-worker", autostart=False)
    # Mock worker as alive
    class DummyProcess:
        pid = 1234
        def is_alive(self):
            return True
        def write(self, *args, **kwargs):
            pass
        def terminate(self):
            pass
    worker.process = DummyProcess()
    worker.state = WorkerProcessState.RUNNING

    threads_before = threading.active_count()

    # Feed 100 chunks in rapid succession
    for i in range(100):
        worker._on_process_output(f"Processing chunk {i}...\r\n")

    # Verify no thread explosion occurred
    threads_after = threading.active_count()
    assert threads_after <= threads_before + 1

    # Wait for debounce window (configured with short wait)
    pipeline._debounce_interval = 0.25
    pipeline.record_activity(worker)
    time.sleep(0.4)

    # Worker must have transitioned to WAITING_INPUT
    assert worker.state == WorkerProcessState.WAITING_INPUT
    TerminalManager.reset()


def test_coordinator_alarm_badge_and_injection() -> None:
    """Coordinator pane receives badges ('⚡ Worker-X Finished (Idle)' or '🚨 Assistance Needed') and terminal injection."""
    TerminalManager.reset()
    mgr = TerminalManager.get_instance()
    mgr.clear_coordinator_alarms()

    coord = mgr.create_worker("coordinator", role="coordinator", autostart=False)
    injected_texts: list[tuple[str, bool]] = []
    class DummyCoordProcess:
        pid = 1234
        def is_alive(self):
            return True
        def write(self, data: str):
            injected_texts.append((data, True))
        def terminate(self):
            pass
    coord.process = DummyCoordProcess()

    # 1. Test idle alarm formatting and badge
    idle_event = mgr.notify_coordinator_worker_idle("1", "Build succeeded")
    assert idle_event["badge"] == "⚡ Worker-1 Finished (Idle)"
    assert idle_event["type"] == "worker_idle"

    tab = WorkerTerminalTab(worker_session=coord)
    tab.set_alarm_badge(idle_event["badge"])
    assert "⚡ Worker-1 Finished (Idle)" in tab._build_header_text()

    # Test injection into coordinator terminal
    injected = mgr.alarm_pipeline.inject_event_to_coordinator(idle_event, press_enter=True)
    assert injected is True
    assert len(injected_texts) == 1
    assert "Worker-1 Finished (Idle)" in injected_texts[0][0]
    assert "Build succeeded" in injected_texts[0][0]

    # 2. Test assistance needed alarm formatting and badge
    help_event = mgr.notify_coordinator_worker_help("2", "Deadlock detected in worker 2", priority="critical")
    assert help_event["badge"] == "🚨 Assistance Needed"
    assert help_event["type"] == "worker_help"

    tab.set_alarm_badge(help_event["badge"])
    header_text = tab._build_header_text()
    assert "🚨 Assistance Needed" in header_text

    injected_help = mgr.alarm_pipeline.inject_event_to_coordinator(help_event, press_enter=True)
    assert injected_help is True
    assert len(injected_texts) == 2
    assert "Assistance Needed" in injected_texts[1][0]
    assert "Deadlock detected in worker 2" in injected_texts[1][0]
    TerminalManager.reset()


def test_extract_target_from_path() -> None:
    """extract_target_from_path maps directive filenames to target agent identifiers."""
    assert extract_target_from_path(Path("~/.mind/directives/coordinator.md")) == "coordinator"
    assert extract_target_from_path(Path("~/.mind/directives/workers/agy1.md")) == "agy1"
    assert extract_target_from_path(Path("~/.mind/directives/workers/agy2.md")) == "agy2"
    assert extract_target_from_path(Path("~/.mind/directives/workers/worker-3.md")) == "agy3"
    assert extract_target_from_path("coordinator.md") == "coordinator"
    assert extract_target_from_path("agy5.md") == "agy5"


def test_directives_watcher_external_modification_detection(tmp_path: Path) -> None:
    """DirectivesWatcher detects external edits to coordinator and worker markdown files."""
    import time

    dirs = tmp_path / "directives"
    workers_dir = dirs / "workers"
    workers_dir.mkdir(parents=True)

    coord_file = dirs / "coordinator.md"
    coord_file.write_text("# Initial Coordinator Rules\nStand by.", encoding="utf-8")
    worker1_file = workers_dir / "agy1.md"
    worker1_file.write_text("# Initial Worker Rules\nWait for tasks.", encoding="utf-8")

    watcher = DirectivesWatcher(directives_dir=dirs, poll_interval=0.1)

    # Initial check: no changes detected yet
    assert len(watcher.check_for_changes()) == 0

    # 1. Simulate external edit to coordinator.md
    time.sleep(0.05)
    coord_file.write_text("# Updated Coordinator Rules\nDecompose tasks dynamically.", encoding="utf-8")

    changes = watcher.check_for_changes()
    assert len(changes) == 1
    assert changes[0][0] == "coordinator"
    assert "Decompose tasks dynamically" in changes[0][2]

    # Subsequent check without changes returns empty
    assert len(watcher.check_for_changes()) == 0

    # 2. Simulate external edit to worker agy1.md
    time.sleep(0.05)
    worker1_file.write_text("# Updated Worker 1 Rules\nExecute build and run pytest.", encoding="utf-8")

    changes2 = watcher.check_for_changes()
    assert len(changes2) == 1
    assert changes2[0][0] == "agy1"
    assert "Execute build and run pytest" in changes2[0][2]

    # 3. Simulate adding a brand new worker file (agy2.md) externally
    time.sleep(0.05)
    worker2_file = workers_dir / "agy2.md"
    worker2_file.write_text("# Brand New Worker 2 Rules\nMonitor memory usage.", encoding="utf-8")

    changes3 = watcher.check_for_changes()
    assert len(changes3) == 1
    assert changes3[0][0] == "agy2"
    assert "Monitor memory usage" in changes3[0][2]

    # Stop watcher
    watcher.stop()


def test_terminal_manager_hot_reload_and_directive_listeners(tmp_path: Path, monkeypatch) -> None:
    """TerminalManager updates session instructions on directive change and notifies listeners."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    TerminalManager.reset()
    mgr = TerminalManager.get_instance()

    # Create coordinator and worker
    coord = mgr.create_worker("coordinator", role="coordinator", autostart=False)
    worker1 = mgr.create_worker("1", assigned_agent="agy1", autostart=False)

    listener_events = []
    def on_directive_updated(target: str, content: str, updated_sessions: list):
        listener_events.append((target, content, updated_sessions))

    mgr.add_directive_listener(on_directive_updated)

    # Apply directive update to coordinator
    new_coord_text = "# Hot-Reloaded Coordinator Directive\nActively orchestrate workers."
    updated_c = mgr.apply_directive_update("coordinator", new_coord_text, source="external")
    assert len(updated_c) == 1
    assert updated_c[0] is coord
    assert coord.instructions == new_coord_text
    assert coord.profile.instructions == new_coord_text

    # Apply directive update to agy1
    new_worker_text = "# Hot-Reloaded Worker 1 Directive\nExecute deterministic git commits."
    updated_w = mgr.apply_directive_update("agy1", new_worker_text, source="external")
    assert len(updated_w) == 1
    assert updated_w[0] is worker1
    assert worker1.instructions == new_worker_text
    assert worker1.profile.instructions == new_worker_text

    # Verify listener was called for both
    assert len(listener_events) == 2
    assert listener_events[0][0] == "coordinator"
    assert listener_events[1][0] == "agy1"

    # Clean up
    mgr.remove_directive_listener(on_directive_updated)
    TerminalManager.reset()


def test_directive_editor_modal_lifecycle(tmp_path: Path, monkeypatch) -> None:
    """DirectiveEditorModal displays current content, allows edits, and saves to disk."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    modal = DirectiveEditorModal(target="agy3", current_content="# Original agy3 Directive")
    assert modal.target == "agy3"
    assert "Original agy3 Directive" in modal.current_content

    # Simulate user typing new text
    modal.text_area = type("DummyTextArea", (), {"text": "# Modified agy3 Rules via Modal\nKeep tests green."})()

    dismiss_results = []
    modal.dismiss = lambda res: dismiss_results.append(res)

    modal.action_save_directive_content()
    assert len(dismiss_results) == 1
    assert "Modified agy3 Rules via Modal" in dismiss_results[0]

    # Verify disk persistence
    saved_text = load_directive("agy3")
    assert "Keep tests green." in saved_text


def test_open_directive_in_editor(tmp_path: Path, monkeypatch) -> None:
    """open_directive_in_editor correctly resolves path and launches system editor."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    ensure_default_directives()

    opened_paths = []
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda p: opened_paths.append(str(p)))
    else:
        import subprocess
        monkeypatch.setattr(subprocess, "Popen", lambda cmd: opened_paths.append(str(cmd[-1])))

    res_path = open_directive_in_editor("agy1")
    assert res_path.exists()
    assert "agy1.md" in res_path.name
    assert len(opened_paths) == 1
    assert "agy1.md" in opened_paths[0]


def test_workspace_directive_shortcuts_and_messages(tmp_path: Path, monkeypatch) -> None:
    """WorkspaceScreen defines directive shortcuts ('o', 'Ctrl+O', 'd', 'Ctrl+D') and message reactions."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    ws = WorkspaceScreen(session_name="test-shortcuts-session", agent_count=2, goal="")

    # Verify bindings include directive actions
    binding_keys = [b[0] for b in ws.BINDINGS]
    assert "o" in binding_keys
    assert "ctrl+o" in binding_keys
    assert "d" in binding_keys
    assert "ctrl+d" in binding_keys

    # Verify active directive target resolution
    target = ws._resolve_active_directive_target()
    assert target in ("agy1", "1")

    # Simulate terminal screen key events
    dummy_session = TerminalManager.get_instance().create_worker("test-w", autostart=False)
    screen_widget = TerminalScreenWidget(worker_session=dummy_session, mode="PTY")

    emitted_messages = []
    screen_widget.post_message = lambda msg: emitted_messages.append(msg)

    # Test Ctrl+O emission
    class DummyKeyEvent:
        def __init__(self, key: str):
            self.key = key
            self.character = ""
        def stop(self):
            pass
        def prevent_default(self):
            pass

    screen_widget.on_key(DummyKeyEvent("ctrl+o"))
    assert len(emitted_messages) == 1
    assert isinstance(emitted_messages[0], TerminalScreenWidget.OpenDirectiveFileRequested)

    # Test Ctrl+D emission
    screen_widget.on_key(DummyKeyEvent("ctrl+d"))
    assert len(emitted_messages) == 2
    assert isinstance(emitted_messages[1], TerminalScreenWidget.OpenDirectiveEditorRequested)
    TerminalManager.reset()
