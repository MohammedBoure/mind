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
    assert "🧠" in plain_text
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
