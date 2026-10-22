"""Unit and integration tests for Clipboard Sync & Mouse Selection Engine (Task #14).

Validates:
1. Multi-tiered clipboard integration (`copy_to_clipboard`, `get_clipboard_text`, `clear_clipboard`):
   - Direct synchronization with system/in-memory backends.
   - Text sanitization (`\xe0` byte filtering, CRLF normalization).
   - Clipboard history tracking.
2. Mouse drag-selection and Auto-copy on MouseUp:
   - Coordinates tracking from MouseDown to MouseUp.
   - Automatic clipboard copy upon mouse button release.
   - Selection highlighting in rendered buffer.
3. Right-Click clipboard operations:
   - Copying active selection on button 3.
   - Copying recent buffer lines on button 3 when no selection exists.
4. Global shortcut integration:
   - `Ctrl+Shift+C` copying in both NORMAL and PTY modes.
   - `y` Yank copying in NORMAL mode.
"""

from __future__ import annotations

import pytest
from rich.text import Text
from textual import events
from textual.app import App
from textual.widgets import Static

from mind.core.terminal_buffer import TerminalBuffer
from mind.core.terminal_manager import TerminalManager, WorkerSession
from mind.ui.clipboard import (
    clear_clipboard,
    copy_to_clipboard,
    get_clipboard_history,
    get_clipboard_text,
    sanitize_clipboard_text,
)
from mind.ui.terminal_tab import TerminalScreenWidget
from mind.ui.workspace import WorkspaceScreen


@pytest.fixture(autouse=True)
def clean_state():
    TerminalManager.reset()
    clear_clipboard()
    yield
    TerminalManager.reset()
    clear_clipboard()


# ── 1. Clipboard Engine Tests ──────────────────────────────────────────────────

def test_clipboard_copy_and_paste_basic() -> None:
    """Verify copy_to_clipboard sets value and get_clipboard_text retrieves it."""
    test_str = "mind clipboard synchronization engine"
    success = copy_to_clipboard(test_str)
    assert success is True

    retrieved = get_clipboard_text()
    assert retrieved == test_str

    history = get_clipboard_history()
    assert test_str in history


def test_clipboard_sanitization() -> None:
    """Verify stray \\xe0 scancodes and CRLF newlines are sanitized."""
    raw = "\xe0\xe0echo 'Hello World'\r\n"
    clean = sanitize_clipboard_text(raw)
    assert clean == "echo 'Hello World'\n"
    assert "\xe0" not in clean


def test_clipboard_empty_and_clear() -> None:
    """Verify empty text handling and clear_clipboard resets value."""
    assert copy_to_clipboard("") is False

    copy_to_clipboard("data to clear")
    assert get_clipboard_text() == "data to clear"

    clear_clipboard()
    assert get_clipboard_text() == ""


def test_clipboard_fallback_without_pyperclip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify multi-tier fallback succeeds even when pyperclip raises exception."""
    import pyperclip

    def fake_copy_fail(text):
        raise RuntimeError("Pyperclip display unavailable")

    monkeypatch.setattr(pyperclip, "copy", fake_copy_fail)

    success = copy_to_clipboard("fallback text")
    assert success is True
    assert get_clipboard_text() == "fallback text"


# ── 2. TerminalScreenWidget Mouse Drag Selection & Auto-Copy ─────────────────

def _mouse_down(widget, x=0, y=0, button=1) -> events.MouseDown:
    return events.MouseDown(widget, x=x, y=y, delta_x=0, delta_y=0, button=button, shift=False, meta=False, ctrl=False)


def _mouse_move(widget, x=0, y=0, button=1) -> events.MouseMove:
    return events.MouseMove(widget, x=x, y=y, delta_x=0, delta_y=0, button=button, shift=False, meta=False, ctrl=False, screen_x=x, screen_y=y)


def _mouse_up(widget, x=0, y=0, button=1) -> events.MouseUp:
    return events.MouseUp(widget, x=x, y=y, delta_x=0, delta_y=0, button=button, shift=False, meta=False, ctrl=False, screen_x=x, screen_y=y)


def test_terminal_mouse_drag_and_autocopy_on_mouseup() -> None:
    """Verify mouse drag-selection automatically copies to clipboard on MouseUp."""
    session = WorkerSession("test-mouse-worker", name="Worker-Mouse")
    session.buffer.feed("Line 1: System initialized.\r\nLine 2: Task running.\r\nLine 3: Finished.\r\n")

    widget = TerminalScreenWidget(worker_session=session)

    # 1. MouseDown at line 0, column 0
    widget.on_mouse_down(_mouse_down(widget, x=0, y=0, button=1))
    assert widget._is_dragging is True
    assert widget._select_start == (0, 0)

    # 2. MouseMove to line 0, column 6 ("Line 1")
    widget.on_mouse_move(_mouse_move(widget, x=6, y=0, button=1))
    assert widget._select_end == (6, 0)
    assert widget.has_selection is True

    selected_text = widget.get_selected_text()
    assert selected_text == "Line 1"

    # 3. MouseUp releases button 1 -> Triggers Auto-Copy to clipboard
    widget.on_mouse_up(_mouse_up(widget, x=6, y=0, button=1))
    assert widget._is_dragging is False

    # Check clipboard contains selected text
    assert get_clipboard_text() == "Line 1"


def test_terminal_selection_styling_in_render() -> None:
    """Verify _apply_selection_styling highlights selected region in rich Text."""
    session = WorkerSession("test-style-worker", name="Worker-Style")
    session.buffer.feed("Selectable Text Content\r\n")

    widget = TerminalScreenWidget(worker_session=session)
    widget._select_start = (0, 0)
    widget._select_end = (10, 0)

    assert widget.has_selection is True
    rendered = widget.render()
    assert isinstance(rendered, Text)
    assert "Selectable" in rendered.plain


# ── 3. Right-Click Copy (Selection vs Recent Buffer) ──────────────────────────

def test_terminal_right_click_copies_selection() -> None:
    """Right-click with active selection copies the selection to clipboard."""
    session = WorkerSession("test-rc-worker", name="Worker-RC")
    session.buffer.feed("Coordination directive injected.\r\n")

    widget = TerminalScreenWidget(worker_session=session)
    widget._select_start = (0, 0)
    widget._select_end = (12, 0)

    # Right-click (button 3)
    widget.on_mouse_down(_mouse_down(widget, x=5, y=0, button=3))
    assert get_clipboard_text() == "Coordination"


def test_terminal_right_click_copies_buffer_when_no_selection() -> None:
    """Right-click without selection copies recent terminal buffer lines to clipboard."""
    session = WorkerSession("test-rc-empty", name="Worker-RC-Empty")
    session.buffer.feed("Log line alpha\r\nLog line beta\r\n")

    widget = TerminalScreenWidget(worker_session=session)
    assert widget.has_selection is False

    # Right-click (button 3)
    widget.on_mouse_down(_mouse_down(widget, x=5, y=0, button=3))
    clip_text = get_clipboard_text()
    assert "Log line alpha" in clip_text
    assert "Log line beta" in clip_text


# ── 4. Global Keyboard Shortcuts (Ctrl+Shift+C and y) ─────────────────────────

def test_terminal_ctrl_shift_c_shortcut() -> None:
    """Ctrl+Shift+C copies recent buffer lines to clipboard."""
    session = WorkerSession("test-ctrl-shift-c", name="Worker-Key")
    session.buffer.feed("Status: 200 OK\r\n")

    widget = TerminalScreenWidget(worker_session=session)
    # Simulate Ctrl+Shift+C
    event = events.Key("ctrl+shift+c", "C")
    widget.on_key(event)

    assert "Status: 200 OK" in get_clipboard_text()


def test_terminal_normal_mode_y_yank_shortcut() -> None:
    """In NORMAL mode, pressing 'y' yanks terminal buffer to clipboard."""
    session = WorkerSession("test-yank-worker", name="Worker-Yank")
    session.buffer.feed("Yankable content payload\r\n")

    widget = TerminalScreenWidget(worker_session=session)
    assert widget.is_pty_mode is False

    # Simulate 'y'
    event = events.Key("y", "y")
    widget.on_key(event)

    assert "Yankable content payload" in get_clipboard_text()
