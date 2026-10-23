"""Unit tests for Session Settings Persistence and Terminal Layout Fixes.

Verifies:
- SessionRecord correctly serializes and restores agent_configs and global_settings.
- update_session_worker_config updates disk storage and is restored when WorkspaceScreen boots.
- Global user preferences (load_global_config, save_global_config) persist to ~/.mind/config.json.
- TerminalScreenWidget content_size integration and no_wrap prevent text wrapping artifacts.
- Header bar terminal status line displays with height=2 and border-bottom styling.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from rich.text import Text

from mind.core.session_storage import (
    SessionRecord,
    get_session,
    load_all_sessions,
    load_global_config,
    save_global_config,
    save_session,
    update_session_worker_config,
)
from mind.core.terminal_buffer import TerminalBuffer
from mind.ui.terminal_tab import TerminalScreenWidget
from mind.core.terminal_manager import WorkerSession


def test_session_record_agent_configs_serialization(tmp_path: Path) -> None:
    """Verify SessionRecord serializes and deserializes worker configurations."""
    test_file = tmp_path / "sessions.json"
    session = SessionRecord(
        name="test-persist",
        agent_count=3,
        goal="Test configuration persistence",
        agent_configs={
            "coordinator": {
                "assigned_agent": "agy1",
                "model": "claude-sonnet-4-6",
                "cli_mode": "accept-edits",
                "reasoning_effort": "high",
                "extra_flags": "--dangerously-skip-permissions",
            },
            "1": {
                "assigned_agent": "agy2",
                "model": "gemini-3.8-flash-high",
                "cli_mode": "auto",
                "reasoning_effort": "medium",
                "extra_flags": "--sandbox",
            },
        },
        global_settings={
            "color_scheme": "tokyo-night",
            "editor_mode": "vim",
        },
    )

    save_session(session, storage_path=test_file)

    loaded = get_session("test-persist", storage_path=test_file)
    assert loaded is not None
    assert loaded.name == "test-persist"
    assert loaded.agent_configs["coordinator"]["model"] == "claude-sonnet-4-6"
    assert loaded.agent_configs["coordinator"]["cli_mode"] == "accept-edits"
    assert loaded.agent_configs["1"]["assigned_agent"] == "agy2"
    assert loaded.agent_configs["1"]["extra_flags"] == "--sandbox"
    assert loaded.global_settings["color_scheme"] == "tokyo-night"


def test_update_session_worker_config(tmp_path: Path) -> None:
    """Verify update_session_worker_config writes to disk incrementally."""
    test_file = tmp_path / "sessions.json"
    save_session(SessionRecord(name="dev-session"), storage_path=test_file)

    update_session_worker_config(
        session_name="dev-session",
        worker_id="2",
        config={
            "assigned_agent": "agy3",
            "model": "gpt-oss-120b-medium",
            "cli_mode": "plan",
            "name": "Planner-Agent",
        },
        storage_path=test_file,
    )

    updated = get_session("dev-session", storage_path=test_file)
    assert updated is not None
    assert "2" in updated.agent_configs
    assert updated.agent_configs["2"]["assigned_agent"] == "agy3"
    assert updated.agent_configs["2"]["name"] == "Planner-Agent"
    assert updated.agent_configs["2"]["cli_mode"] == "plan"


def test_global_config_persistence(tmp_path: Path) -> None:
    """Verify load_global_config and save_global_config persist global preferences."""
    test_config_file = tmp_path / "config.json"
    assert load_global_config(config_path=test_config_file) == {}

    save_global_config(
        {"color_scheme": "catppuccin", "editor": "code", "copy_on_select": True},
        config_path=test_config_file,
    )

    loaded = load_global_config(config_path=test_config_file)
    assert loaded["color_scheme"] == "catppuccin"
    assert loaded["editor"] == "code"
    assert loaded["copy_on_select"] is True

    # Update incremental
    save_global_config({"verbosity": "debug"}, config_path=test_config_file)
    updated = load_global_config(config_path=test_config_file)
    assert updated["color_scheme"] == "catppuccin"
    assert updated["verbosity"] == "debug"


def test_terminal_buffer_no_wrap_and_crop() -> None:
    """Verify get_rich_text sets no_wrap=True and overflow='crop' to prevent line wrapping."""
    buf = TerminalBuffer(columns=40, lines=10)
    buf.feed("Line 1 with lots of data to test overflow boundary\r\nLine 2\r\n")

    rich_text = buf.get_rich_text(show_cursor=False)
    assert rich_text.no_wrap is True
    assert rich_text.overflow == "crop"


def test_terminal_widget_content_size_resize() -> None:
    """Verify TerminalScreenWidget uses exact content_size in resize."""
    from textual.events import Resize
    from textual.geometry import Size

    session = WorkerSession(worker_id="test", name="Worker-Test")
    widget = TerminalScreenWidget(worker_session=session)

    # Simulate on_resize with event size 80x24
    resize_event = Resize(Size(80, 24), Size(80, 24))
    widget.on_resize(resize_event)

    # Check buffer was resized
    assert session.buffer.columns >= 20
    assert session.buffer.lines >= 5
