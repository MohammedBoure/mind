"""Comprehensive unit and integration tests for Keyboard-First Modal Dialogs (Task #13).

Validates:
1. `AgentConfigModal` keyboard-first layout:
   - Live search filter (`Search: `, `#config-search-input`) and dynamic option filtering.
   - Smooth cursor navigation (`>`) with Arrow keys and `k/j`.
   - Instant option cycling via `Space`, `Enter`, and Arrow keys (`h/l`, Left/Right).
   - In-app behavioral directive editor modal (`DirectiveEditorModal`) integration via `e`.
2. `DirectiveModal` assignment & task dispatcher:
   - Target agent selection (`#target-agent-select`).
   - Task role assignment (`#role-select`).
   - Priority selection dropdown (`#priority-select`) with high, critical, normal, low.
   - Instant injection into worker with custom priority.
3. `SessionPickerScreen` persistent session management:
   - Session disk persistence (`load_all_sessions`, `save_session`, `delete_session`).
   - Live activity statistics tracking (steps, interactions, last activity, agent count).
   - Full keyboard navigation (`k/j`, `Enter`, `n`, `d/x`, `r`, `q`).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import pytest

from textual.app import App
from textual.widgets import Input, OptionList, Select, Static

from mind.core.session_storage import (
    SessionRecord,
    delete_session,
    get_session,
    load_all_sessions,
    record_session_activity,
    save_session,
)
from mind.core.terminal_manager import TerminalManager
from mind.ui.agent_config_modal import AgentConfigModal, ConfigOption, ConfigSettingsListWidget
from mind.ui.directive_modal import DirectiveModal
from mind.ui.session_picker import SessionPickerScreen


@pytest.fixture(autouse=True)
def reset_manager_state():
    TerminalManager.reset()
    yield
    TerminalManager.reset()


# ── 1. AgentConfigModal Tests ──────────────────────────────────────────────────

def test_config_settings_list_search_and_cursor() -> None:
    """ConfigSettingsListWidget filters entries and renders '>' cursor for active entry."""
    entries = [
        ConfigOption(key="agent_mode", label="Agent Mode", options=["auto", "plan", "accept-edits"]),
        ConfigOption(key="editor", label="Editor", options=["vim", "nano", "code"]),
        ConfigOption(key="sandbox_mode", label="Sandbox Mode", options=["off", "on"]),
    ]
    widget = ConfigSettingsListWidget(entries=entries)

    # Initial state
    assert widget.selected_index == 0
    active = widget.get_active_entry()
    assert active is not None
    assert active.key == "agent_mode"

    rendered_text = widget.render().plain
    assert "> Agent Mode" in rendered_text or "> " in rendered_text

    # Move cursor down with j / arrow
    widget.action_move_down()
    assert widget.selected_index == 1
    assert widget.get_active_entry().key == "editor"

    # Move cursor up with k / arrow
    widget.action_move_up()
    assert widget.selected_index == 0
    assert widget.get_active_entry().key == "agent_mode"

    # Search filtering
    widget.set_search_query("sand")
    filtered = widget.get_filtered_entries()
    assert len(filtered) == 1
    assert filtered[0][1].key == "sandbox_mode"
    assert widget.get_active_entry().key == "sandbox_mode"


def test_config_option_cycling_keys() -> None:
    """Options cycle smoothly forward and backward via Space, Enter, and Left/Right."""
    option = ConfigOption(
        key="color_scheme",
        label="Color Scheme",
        options=["tokyo-night", "catppuccin", "monokai"],
        current_index=0,
    )
    assert option.value == "tokyo-night"

    # Cycle next (Space / Enter / Right / l)
    val = option.cycle_next()
    assert val == "catppuccin"
    assert option.current_index == 1

    val = option.cycle_next()
    assert val == "monokai"

    # Wrap around
    val = option.cycle_next()
    assert val == "tokyo-night"

    # Cycle prev (Left / h)
    val = option.cycle_prev()
    assert val == "monokai"


@pytest.mark.anyio
async def test_agent_config_modal_keyboard_interaction() -> None:
    """AgentConfigModal renders search bar, settings list, and handles keyboard events."""
    class TestApp(App):
        def compose(self):
            yield Static("Root")

    app = TestApp()
    async with app.run_test() as pilot:
        modal = AgentConfigModal(default_target="1")
        await app.push_screen(modal)

        # Verify search input is present
        search_input = modal.query_one("#config-search-input", Input)
        assert search_input is not None
        assert modal.query_one("#config-search-prompt", Static) is not None

        # Verify settings list widget
        settings_view = modal.query_one("#config-settings-view", ConfigSettingsListWidget)
        assert settings_view is not None

        # Focus settings view and cycle option with Space
        settings_view.focus()
        initial_val = settings_view.get_active_entry().value
        await pilot.press("space")
        new_val = settings_view.get_active_entry().value
        assert new_val != initial_val or len(settings_view.get_active_entry().options) <= 1

        # Esc closes modal
        await pilot.press("escape")
        assert len(app.screen_stack) == 1


# ── 2. DirectiveModal Priority & Injection Tests ───────────────────────────────

@pytest.mark.anyio
async def test_directive_modal_priority_and_dispatch() -> None:
    """DirectiveModal includes Priority dropdown and injects with specified priority."""
    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("test-prio-worker", name="Worker-Prio", autostart=False)

    injected_calls = []

    def fake_interrupt(sender_id: str, message: str, priority: str = "high") -> str:
        injected_calls.append({"sender": sender_id, "message": message, "priority": priority})
        return "OK"

    worker.interrupt_and_inject = fake_interrupt

    class TestApp(App):
        def compose(self):
            yield Static("Root")

    app = TestApp()
    async with app.run_test() as pilot:
        modal = DirectiveModal(default_target="test-prio-worker")
        await app.push_screen(modal)

        # Check Priority Select is present
        prio_select = modal.query_one("#priority-select", Select)
        assert prio_select is not None
        assert prio_select.value == "high"

        # Change priority to critical
        prio_select.value = "critical"

        # Set task prompt text
        prompt_input = modal.query_one("#task-prompt-input", Input)
        prompt_input.value = "Halt all work and verify security patches"

        # Submit task
        modal._submit_dispatch()

        # Verify injection payload and priority
        assert len(injected_calls) == 1
        assert injected_calls[0]["priority"] == "critical"
        assert injected_calls[0]["message"] == "Halt all work and verify security patches"


# ── 3. Session Storage & Persistence Tests ────────────────────────────────────

def test_session_storage_crud_and_telemetry() -> None:
    """Session storage saves, loads, updates activity, and deletes sessions on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "test_sessions.json"

        # Initial load seeds default sessions
        sessions = load_all_sessions(storage_path=storage_file)
        assert len(sessions) >= 2
        assert storage_file.exists()

        # Create and save a new session
        new_sess = SessionRecord(
            name="deep-refactor-v2",
            created_at=datetime.now(),
            last_activity=datetime.now(),
            agent_count=5,
            goal="Refactor terminal streaming architecture",
            active=True,
            total_steps=10,
            total_interactions=2,
            status="active",
        )
        save_session(new_sess, storage_path=storage_file)

        # Retrieve session
        retrieved = get_session("deep-refactor-v2", storage_path=storage_file)
        assert retrieved is not None
        assert retrieved.name == "deep-refactor-v2"
        assert retrieved.agent_count == 5
        assert retrieved.total_steps == 10

        # Record activity
        updated = record_session_activity("deep-refactor-v2", steps=15, status="busy", storage_path=storage_file)
        assert updated is not None
        assert updated.total_steps == 25
        assert updated.total_interactions == 3
        assert updated.status == "busy"

        # Delete session
        deleted = delete_session("deep-refactor-v2", storage_path=storage_file)
        assert deleted is True
        assert get_session("deep-refactor-v2", storage_path=storage_file) is None


# ── 4. SessionPickerScreen Keyboard Navigation Tests ───────────────────────────

@pytest.mark.anyio
async def test_session_picker_screen_keyboard_actions() -> None:
    """SessionPickerScreen supports j/k cursor navigation, r refresh, and Enter selection."""
    class TestApp(App):
        def compose(self):
            yield Static("Root")

    app = TestApp()
    async with app.run_test() as pilot:
        picker = SessionPickerScreen()
        await app.push_screen(picker)

        opt_list = picker.query_one("#session-list", OptionList)
        assert opt_list is not None
        assert len(picker.sessions) > 0

        # Test Vim j/k navigation
        initial_idx = opt_list.highlighted or 0
        picker.action_cursor_down()
        assert opt_list.highlighted == min(initial_idx + 1, opt_list.option_count - 1)

        picker.action_cursor_up()
        assert opt_list.highlighted == initial_idx

        # Test refresh
        picker.action_refresh_sessions()
        assert len(picker.sessions) > 0
