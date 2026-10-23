"""Unit tests verifying removal of internal principles injection, .GEMINI.md integration, and direct text input for system agent."""

from __future__ import annotations

from pathlib import Path
import pytest
from unittest.mock import MagicMock

from textual.app import App
from textual.widgets import Input, Static

from mind.core.alarm_pipeline import CoordinatorAlarmPipeline
from mind.core.directives import (
    DEFAULT_COORDINATOR_DIRECTIVE,
    DEFAULT_WORKER_DIRECTIVE_TEMPLATE,
    get_instance_gemini_path,
    resolve_directive_path,
)
from mind.core.terminal_manager import AgentProfile, TerminalManager, WorkerSession
from mind.ui.agent_config_modal import AgentConfigModal, ConfigOption


@pytest.fixture(autouse=True)
def reset_manager_state():
    TerminalManager.reset()
    yield
    TerminalManager.reset()


def test_agent_profile_principles_cleared() -> None:
    """AgentProfile and WorkerSession have empty internal principles and no synthetic injection."""
    profile = AgentProfile(agent_id="test-agent")
    assert profile.principles == []
    assert profile.instructions == ""

    # Check default directives templates have no hardcoded principles
    assert "## Principles" not in DEFAULT_WORKER_DIRECTIVE_TEMPLATE
    assert "## Principles" not in DEFAULT_COORDINATOR_DIRECTIVE
    assert "Managed directly via .GEMINI.md" in DEFAULT_WORKER_DIRECTIVE_TEMPLATE

    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("worker-test", assigned_agent="agy1", autostart=False)
    prof_dict = worker.get_profile_dict()
    assert "principles" in prof_dict
    assert prof_dict["principles"] == []


def test_alarm_pipeline_no_coordinator_directive_injection() -> None:
    """Coordinator alarms must not inject synthetic 'Coordinator Directive:' lines."""
    mgr = TerminalManager.get_instance()
    coord = mgr.create_worker("coordinator", role="coordinator", autostart=False)
    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    coord.process = mock_proc
    coord.write = MagicMock()

    pipeline = CoordinatorAlarmPipeline(manager=mgr)
    event = {
        "type": "worker_idle",
        "worker_id": "2",
        "summary": "Completed linting successfully",
    }
    injected = pipeline.inject_event_to_coordinator(event)
    assert injected is True
    assert coord.write.call_count == 1
    call_args = coord.write.call_args[0][0]
    assert "[Worker-2 Finished (Idle)]" in call_args
    assert "Coordinator Directive:" not in call_args

    # Check worker_help event
    coord.write.reset_mock()
    help_event = {
        "type": "worker_help",
        "worker_id": "3",
        "summary": "Need credentials",
        "priority": "critical",
    }
    injected_help = pipeline.inject_event_to_coordinator(help_event)
    assert injected_help is True
    help_args = coord.write.call_args[0][0]
    assert "[Assistance Needed from Worker-3 | Priority: CRITICAL]" in help_args
    assert "Coordinator Directive:" not in help_args


def test_gemini_path_resolution(tmp_path: Path, monkeypatch) -> None:
    """Verify resolution resolves to .GEMINI.md when instance directory exists."""
    # Setup mock agy-instances directory
    instances_dir = tmp_path / ".local" / "share" / "agy-instances"
    slot_gemini = instances_dir / "agy1" / ".gemini"
    slot_gemini.mkdir(parents=True, exist_ok=True)
    gemini_file = slot_gemini / ".GEMINI.md"
    gemini_file.write_text("# Instance 1 Rules\nDo not bypass safety.", encoding="utf-8")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    path = get_instance_gemini_path("agy1")
    assert path is not None
    assert path.resolve() == gemini_file.resolve()

    resolved = resolve_directive_path("agy1")
    assert resolved.resolve() == gemini_file.resolve()


@pytest.mark.anyio
async def test_agent_config_modal_direct_system_agent_input() -> None:
    """AgentConfigModal provides direct text input (#config-agent-input) for system agent."""
    mgr = TerminalManager.get_instance()
    mgr.create_worker("coordinator", role="coordinator", assigned_agent="agy1", autostart=False)
    worker1 = mgr.create_worker("1", role="worker", assigned_agent="agy2", autostart=False)

    class TestApp(App):
        def compose(self):
            yield Static("Root")

    app = TestApp()
    async with app.run_test() as pilot:
        modal = AgentConfigModal(default_target="1")
        await app.push_screen(modal)

        # 1. Verify direct agent input field exists and is populated with Tab 1's agent (agy2)
        agent_input = modal.query_one("#config-agent-input", Input)
        assert agent_input is not None
        assert agent_input.value == "agy2"

        # 2. Type new agent name 'agy125' directly as text
        agent_input.value = "agy125"
        agent_input.post_message(Input.Changed(agent_input, "agy125"))
        await pilot.pause()

        # Verify system_agent option updated instantaneously
        sys_opt = next(opt for opt in modal.options if opt.key == "system_agent")
        assert sys_opt.value == "agy125"

        # 3. Save and close
        modal.action_save_and_close()
        assert worker1.assigned_agent == "agy125"
        assert worker1.name == "agy125"
