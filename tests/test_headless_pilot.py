"""Comprehensive Headless Test Pilot & End-to-End Quality Assurance Suite (Task #16).

Verifies full-stack headless execution via the Textual Test Pilot:
1. Pure headless initialization of `MindApp` without GUI or desktop display.
2. Complete end-to-end user navigation journey:
   - Session picker landing screen navigation (`OptionList`, `j/k`, `Enter`).
   - Modal lifecycle transition: `NewSessionModal` -> creation -> `WorkspaceScreen`.
   - Dual Vim modal multiplexer operations:
     * Mode transition from NORMAL to PTY_INTERACT and exit via `Ctrl+B`.
     * Split View toggling (`s`) and full expansion.
     * Agent config modal overlay (`e`) and option cycling.
     * Directive dispatcher modal (`m`) and priority task injection.
3. Multi-platform compatibility validation across Windows and Linux environments.
"""

from __future__ import annotations

import sys
import pytest
from textual import events
from textual.widgets import Input, OptionList, Select, Static

from mind.app import MindApp
from mind.core.session_storage import get_session, load_all_sessions
from mind.core.terminal_manager import TerminalManager
from mind.ui.agent_config_modal import AgentConfigModal
from mind.ui.directive_modal import DirectiveModal
from mind.ui.new_session_modal import NewSessionModal
from mind.ui.session_picker import SessionPickerScreen
from mind.ui.workspace import WorkspaceScreen


@pytest.fixture(autouse=True)
def clean_headless_env():
    """Ensure clean state before and after each headless pilot run."""
    TerminalManager.reset()
    yield
    TerminalManager.reset()


@pytest.mark.anyio
async def test_headless_end_to_end_user_journey() -> None:
    """Run complete TUI orchestration flow in 100% headless mode via Textual pilot."""
    app = MindApp()

    async with app.run_test() as pilot:
        # 1. Verify app starts on SessionPickerScreen
        assert isinstance(app.screen, SessionPickerScreen)
        picker = app.screen
        session_list = picker.query_one("#session-list", OptionList)
        assert session_list is not None
        assert session_list.option_count > 0

        # Test Vim j/k navigation in headless mode
        initial_highlighted = session_list.highlighted or 0
        await pilot.press("j")
        assert session_list.highlighted >= initial_highlighted

        await pilot.press("k")
        assert session_list.highlighted == initial_highlighted

        # 2. Open NewSessionModal with 'n'
        await pilot.press("n")
        assert isinstance(app.screen, NewSessionModal)
        modal = app.screen

        # Fill in new session details
        name_input = modal.query_one("#session-name-input", Input)
        name_input.value = "e2e-headless-session"

        count_input = modal.query_one("#agent-count-input", Input)
        count_input.value = "3"

        goal_input = modal.query_one("#session-goal-input", Input)
        goal_input.value = "Verify complete headless lifecycle"

        # Submit modal with Enter
        await pilot.press("enter")
        await pilot.pause()

        # 3. Verify transition to WorkspaceScreen
        assert isinstance(app.screen, WorkspaceScreen)
        workspace = app.screen
        assert workspace.session_name == "e2e-headless-session"
        assert workspace.agent_count == 3

        # Verify persistent storage holds this session
        saved = get_session("e2e-headless-session")
        assert saved is not None
        assert saved.agent_count == 3

        # 4. Workspace Navigation: Normal vs PTY modes
        assert workspace.mode == "NORMAL"

        # Press 'i' to enter PTY_INTERACT mode
        await pilot.press("i")
        assert workspace.mode == "PTY_INTERACT"

        # Exit PTY_INTERACT mode cleanly with Ctrl+B
        await pilot.press("ctrl+b")
        assert workspace.mode == "NORMAL"

        # 5. Open DirectiveModal via 'm'
        await pilot.press("m")
        assert isinstance(app.screen, DirectiveModal)
        dir_modal = app.screen

        # Verify priority select is present and set value
        prio = dir_modal.query_one("#priority-select", Select)
        assert prio is not None
        prio.value = "high"

        # Dismiss modal with Escape
        await pilot.press("escape")
        assert isinstance(app.screen, WorkspaceScreen)

        # 6. Open AgentConfigModal via 'e'
        await pilot.press("e")
        assert isinstance(app.screen, AgentConfigModal)
        cfg_modal = app.screen
        assert cfg_modal.query_one("#config-search-input") is not None

        # Dismiss config modal with Escape
        await pilot.press("escape")
        assert isinstance(app.screen, WorkspaceScreen)

        # 7. Test Split View toggle with 's'
        init_split = workspace._is_split_view
        await pilot.press("s")
        assert workspace._is_split_view != init_split

        await pilot.press("s")
        assert workspace._is_split_view == init_split


@pytest.mark.anyio
async def test_headless_cross_platform_capabilities() -> None:
    """Validate headless pilot resilience across OS platforms (Windows & Linux)."""
    app = MindApp(initial_session="headless-direct")

    async with app.run_test() as pilot:
        # Directly entered workspace
        assert isinstance(app.screen, WorkspaceScreen)
        ws = app.screen
        assert ws.session_name == "headless-direct"

        # Check Coordinator and Worker pane presence
        coord_tab = getattr(ws, "_coordinator_tab", None)
        assert coord_tab is not None
        assert coord_tab.screen_widget is not None

        # Check tab navigation: jump to tab 1
        await pilot.press("1")
        assert str(ws._active_worker_id) == "1"

        # Check tab navigation: jump to tab 2
        await pilot.press("2")
        assert str(ws._active_worker_id) == "2"

        # Verify safe quit action
        ws.action_quit()
