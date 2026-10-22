"""Unit tests for Tokyo Night & Modern TUI Styling (Task #10).

Verifies:
- Textual stylesheet parsing and Tokyo Night color palette rules
- Rounded borders across modals, terminal screens, and interactive controls
- Intelligent visual separation between Coordinator pane and Worker panes
- Unicode, Arabic characters, and Nerd Fonts glyph compatibility
"""

from __future__ import annotations

from pathlib import Path
import pytest
from rich.text import Text
from textual.app import App
from textual.widgets import Static

from mind.app import MindApp, _CSS_PATH
from mind.core.terminal_manager import WorkerProcessState, WorkerSession
from mind.ui.bottom_bar import BottomBar
from mind.ui.header_bar import HeaderBar
from mind.ui.terminal_tab import TerminalScreenWidget, WorkerTabBar, WorkerTerminalTab


def test_styles_tcss_file_exists_and_parses() -> None:
    """Verify that styles.tcss exists and is valid Textual CSS without syntax errors."""
    assert _CSS_PATH.exists()
    content = _CSS_PATH.read_text(encoding="utf-8")
    assert len(content) > 500

    # Test loading in a mock Textual App
    class StyleTestApp(App):
        CSS_PATH = _CSS_PATH

    app = StyleTestApp()
    # Parsing the CSS rules must succeed without error
    css_rules = app.stylesheet
    assert css_rules is not None


def test_tokyo_night_color_palette_and_rounded_borders() -> None:
    """Verify Tokyo Night high-contrast colors and rounded border definitions in stylesheet."""
    css = _CSS_PATH.read_text(encoding="utf-8")

    # Tokyo Night dark backgrounds
    assert "#1a1b26" in css  # Screen root canvas
    assert "#16161e" in css  # Docked bars & dialog background
    assert "#13141f" in css  # Coordinator terminal canvas
    assert "#0f141c" in css  # Worker terminal canvas

    # High-contrast Tokyo Night foreground & accents
    assert "#c0caf5" in css  # Crisp foreground
    assert "#bb9af7" in css  # Coordinator violet
    assert "#7aa2f7" in css  # Worker blue
    assert "#e0af68" in css  # Warm gold / Normal mode
    assert "#9ece6a" in css  # Green success
    assert "#f7768e" in css  # Red warning / error

    # Rounded borders (Zellij / Modern TUI aesthetic)
    assert "border: round" in css
    assert "#primary-pane .terminal-screen" in css
    assert "#workers-pane .terminal-screen" in css
    assert "#directive-modal-dialog" in css
    assert "#agent-config-dialog" in css
    assert "#help-dialog" in css
    assert "#picker-panel" in css
    assert "#new-session-dialog" in css
    assert "#directive-editor-dialog" in css


def test_smart_coordinator_and_worker_separation() -> None:
    """Verify distinct styling separating Coordinator pane from Worker windows."""
    css = _CSS_PATH.read_text(encoding="utf-8")

    # Coordinator pane rules
    assert "#primary-pane" in css
    assert "border-right: solid #292e42" in css
    assert "#primary-pane .terminal-header" in css
    assert "border-bottom: solid #bb9af7" in css  # Distinct purple header accent

    # Worker pane rules
    assert "#workers-pane" in css
    assert "#workers-pane .terminal-header" in css
    assert "border-bottom: solid #3b4261" in css
    assert ".worker-tab-pill.-active" in css
    assert "background: #7aa2f7" in css


def test_unicode_and_arabic_tab_title_formatting() -> None:
    """Verify that WorkerTabBar handles Arabic and Unicode titles cleanly without clipping."""
    arabic_name = "مطور الواجهة (Frontend Agent)"
    tab_title = WorkerTabBar._format_tab_title("2", arabic_name, is_active=True)

    assert "مطور الواجهة" in tab_title
    assert "[2]" in tab_title
    assert "Worker-2" in tab_title

    # Chinese / Kanji Unicode name
    unicode_name = "コード作成者 (Coder)"
    tab_title_jp = WorkerTabBar._format_tab_title("3", unicode_name, is_active=False)
    assert "コード作成者" in tab_title_jp
    assert "[3]" in tab_title_jp


def test_nerd_fonts_and_unicode_symbols_in_bars_and_banners() -> None:
    """Verify Nerd Fonts and Unicode emojis in header, status bar, and terminal banner."""
    header = HeaderBar(session_name="جلسة-رئيسية", worker_count=3, mode="NORMAL")
    assert header.session_name == "جلسة-رئيسية"

    bottom = BottomBar(worker_count=3, mode="NORMAL")
    mode_text = bottom._build_mode_indicator()
    # Emojis and icons present in modal indicators
    assert "🔍" in mode_text or "NORMAL" in mode_text

    bottom_pty = BottomBar(worker_count=3, mode="PTY")
    mode_pty_text = bottom_pty._build_mode_indicator()
    assert "⌨" in mode_pty_text or "PTY" in mode_pty_text

    # Placeholder banner contains Unicode rounded box drawing glyphs and icons
    session = WorkerSession(worker_id="coord", name="المنسق العام", role="coordinator")
    widget = TerminalScreenWidget(worker_session=session, mode="NORMAL")
    banner = widget._render_placeholder_banner()
    plain_text = banner.plain

    # Verify rounded Unicode box borders
    assert "╭" in plain_text
    assert "╰" in plain_text
    assert "mind" in plain_text
    assert "المنسق العام" in plain_text


@pytest.mark.anyio
async def test_app_mounts_with_tokyo_night_stylesheet() -> None:
    """Verify that MindApp boots up headless using Textual Test Pilot without CSS errors."""
    app = MindApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        assert app.is_running
        # Global stylesheet must be applied
        assert app.stylesheet is not None


def test_interactive_tab_bar_activity_icons_and_formatting() -> None:
    """Test WorkerTabBar activity icons, unclipped tab formatting, and dynamic updates."""
    from mind.core.terminal_manager import TerminalManager, WorkerProcessState

    TerminalManager.reset()
    mgr = TerminalManager.get_instance()

    # Create worker sessions with varying operational states
    w1 = mgr.create_worker("1", name="Worker-1", autostart=False)
    w2 = mgr.create_worker("2", name="agy2", autostart=False)
    w3 = mgr.create_worker("3", name="مهندس البرمجيات", autostart=False)

    # 1. Standby / Unstarted worker -> '○'
    icon_standby = WorkerTabBar._get_activity_icon("1")
    assert icon_standby == "○"

    # 2. Simulate running state -> '●'
    w1.process = type("MockProcess", (), {"is_alive": lambda self: True})()
    w1.state = WorkerProcessState.RUNNING
    icon_running = WorkerTabBar._get_activity_icon("1")
    assert icon_running == "●"

    # 3. Simulate waiting input state -> '…'
    w2.process = type("MockProcess", (), {"is_alive": lambda self: True})()
    w2.state = WorkerProcessState.WAITING_INPUT
    icon_waiting = WorkerTabBar._get_activity_icon("2")
    assert icon_waiting == "…"

    # 4. Simulate unread notification state -> '!'
    w3.unread_notifications = 2
    icon_unread = WorkerTabBar._get_activity_icon("3")
    assert icon_unread == "!"

    # 5. Formatted titles include activity icons and full unclipped names
    tab_bar = WorkerTabBar(
        active_worker_id="1",
        workers=[("1", "Worker-1"), ("2", "agy2"), ("3", "مهندس البرمجيات")],
    )
    t1 = tab_bar._format_tab_title("1", "Worker-1", is_active=True)
    assert "●" in t1
    assert "[1] agy1 (Worker-1)" in t1

    t3 = tab_bar._format_tab_title("3", "مهندس البرمجيات", is_active=False)
    assert "!" in t3
    assert "مهندس البرمجيات · Worker-3" in t3

    # 6. Test update_tab_title
    tab_bar.update_tab_title("2", name="Worker-Custom", activity_icon="*")
    matching = [name for wid, name in tab_bar.tab_items if wid == "2"]
    assert matching == ["Worker-Custom"]


@pytest.mark.anyio
async def test_header_bar_branding_telemetry_and_live_quota_badge() -> None:
    """Test HeaderBar branding, session info, worker telemetry, MCP status, and Live Quota Badge."""
    from textual.app import App

    class HeaderTestApp(App):
        def compose(self):
            yield HeaderBar(
                session_name="production-run",
                worker_count=4,
                mode="NORMAL",
            )

    app = HeaderTestApp()
    async with app.run_test() as pilot:
        header = app.query_one(HeaderBar)
        assert header.session_name == "production-run"
        assert header.worker_count == 4
        assert header.mcp_port == 8765

        # Brand and session pills
        brand = app.query_one("#brand-pill", Static)
        assert "mind" in str(brand.render())

        session = app.query_one("#session-pill", Static)
        assert "production-run" in str(session.render())

        # Worker count pill
        workers = app.query_one("#worker-count-pill", Static)
        assert "4" in str(workers.render())
        assert "active workers" in str(workers.render())

        # MCP status indicator
        mcp = app.query_one("#mcp-indicator", Static)
        assert "MCP" in str(mcp.render())
        assert ":8765" in str(mcp.render())

        # Live Quota Badge
        quota_pill = app.query_one("#quota-pill", Static)
        assert quota_pill is not None
        assert "Quota:" in str(quota_pill.render())

        # Test updating quota badge dynamically
        header.update_quota(remaining_percent=75.0, status="normal")
        await pilot.pause()
        assert "75%" in str(quota_pill.render())

        # Warning status
        header.update_quota(remaining_percent=20.0, status="warning")
        await pilot.pause()
        assert "20%" in str(quota_pill.render())


@pytest.mark.anyio
async def test_bottom_bar_action_pills_modal_and_architecture() -> None:
    """Test BottomBar mode indicator, clickable ActionPills, and PTY architecture badge."""
    from textual.app import App

    triggered_actions = []

    class BottomTestApp(App):
        def compose(self):
            yield BottomBar(worker_count=3, mode="NORMAL", pty_backend="POSIX PTY")

        def action_enter_pty(self):
            triggered_actions.append("enter_pty")

        def action_open_directive_modal(self):
            triggered_actions.append("open_directive_modal")

    app = BottomTestApp()
    async with app.run_test() as pilot:
        bottom = app.query_one(BottomBar)

        # 1. Mode indicator in NORMAL mode
        mode_pill = app.query_one("#bottom-mode-pill", Static)
        assert "NORMAL MODE" in str(mode_pill.render())
        assert "Press 'i' to type in agy" in str(mode_pill.render())

        # 2. PTY platform architecture badge
        status_pill = app.query_one("#bottom-status-pill", Static)
        assert "POSIX PTY" in str(status_pill.render())
        assert "UTF-8" in str(status_pill.render())

        # Dynamic backend update
        bottom.pty_backend = "ConPTY"
        await pilot.pause()
        assert "ConPTY" in str(status_pill.render())

        # 3. ActionPills clickable trigger
        pill_insert = app.query_one("#pill-insert", Static)
        await pill_insert.on_click()
        await pilot.pause()
        assert "enter_pty" in triggered_actions

        pill_inject = app.query_one("#pill-inject", Static)
        await pill_inject.on_click()
        await pilot.pause()
        assert "open_directive_modal" in triggered_actions

        # 4. Mode switch to PTY_INTERACT updates indicator and toggles action boxes
        bottom.mode = "PTY_INTERACT"
        await pilot.pause()
        assert "PTY INTERACT" in str(mode_pill.render())
        assert "Press Esc Esc or Ctrl+B for Outer Normal" in str(mode_pill.render())

        normal_box = app.query_one("#bottom-normal-actions")
        pty_box = app.query_one("#bottom-pty-actions")
        assert normal_box.styles.display == "none"
        assert pty_box.styles.display == "block"


@pytest.mark.asyncio
async def test_worker_tab_bar_rebuild_persistence() -> None:
    """Verify WorkerTabBar.rebuild preserves tab pills without disappearing or DuplicateIds."""
    from mind.ui.terminal_tab import WorkerTabBar, WorkerTabPill, WorkerNewTabPill

    class TabBarApp(App):
        def compose(self):
            yield WorkerTabBar(
                active_worker_id="1",
                workers=[("1", "agy2")],
                id="test-tab-bar",
            )

    app = TabBarApp()
    async with app.run_test() as pilot:
        tab_bar = app.query_one("#test-tab-bar", WorkerTabBar)
        assert len(tab_bar.query(WorkerTabPill)) == 1
        assert app.query_one("#tab-pill-1", WorkerTabPill) is not None
        assert app.query_one("#tab-pill-new", WorkerNewTabPill) is not None

        # 1. Add Tab 2 (e.g. agy11)
        tab_bar.rebuild(workers=[("1", "agy2"), ("2", "agy11")], active_worker_id="2")
        await pilot.pause()
        pills = list(tab_bar.query(WorkerTabPill))
        assert len(pills) == 2
        assert app.query_one("#tab-pill-1", WorkerTabPill) is not None
        assert app.query_one("#tab-pill-2", WorkerTabPill) is not None
        assert app.query_one("#tab-pill-new", WorkerNewTabPill) is not None
        assert app.query_one("#tab-pill-2", WorkerTabPill).is_active is True

        # 2. Add Tab 3
        tab_bar.rebuild(workers=[("1", "agy2"), ("2", "agy11"), ("3", "agy51")], active_worker_id="3")
        await pilot.pause()
        assert len(tab_bar.query(WorkerTabPill)) == 3
        assert app.query_one("#tab-pill-3", WorkerTabPill) is not None

        # 3. Close Tab 2
        tab_bar.rebuild(workers=[("1", "agy2"), ("3", "agy51")], active_worker_id="1")
        await pilot.pause()
        assert len(tab_bar.query(WorkerTabPill)) == 2
        assert app.query_one("#tab-pill-1", WorkerTabPill).is_active is True
        assert len(tab_bar.query("#tab-pill-2")) == 0


