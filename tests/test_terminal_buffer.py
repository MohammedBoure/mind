"""Comprehensive unit tests for the Ultra-Fast Screen Buffer & Rendering Engine (TerminalBuffer)."""

from __future__ import annotations

import threading
import time

import pyte
import pytest
from rich.style import Style
from rich.text import Text

from mind.core.terminal_buffer import (
    TerminalBuffer,
    _resolve_color,
    _STYLE_CACHE,
    strip_ansi,
)


class TestTerminalBuffer2DGrid:
    """Test 2D grid structure, dimensions, cursor positioning, and basic operations."""

    def test_initialization_defaults(self) -> None:
        buf = TerminalBuffer(columns=80, lines=24, history_size=500)
        assert buf.columns == 80
        assert buf.lines == 24
        assert buf.history_size == 500
        assert buf.version == 0
        assert buf.has_content is False
        assert buf.cursor == (0, 0)

    def test_minimum_dimensions_enforced(self) -> None:
        buf = TerminalBuffer(columns=10, lines=2, history_size=2)
        assert buf.columns == 20  # minimum clamped to 20
        assert buf.lines == 5     # minimum clamped to 5
        assert buf.history_size == 10  # minimum clamped to 10

    def test_cursor_movement_and_coordinates(self) -> None:
        buf = TerminalBuffer(columns=80, lines=24)
        buf.feed("Hello\r\nWorld")
        y, x = buf.cursor
        assert y == 1
        assert x == 5

    def test_get_char_and_get_line(self) -> None:
        buf = TerminalBuffer(columns=80, lines=24)
        buf.feed("Line 1\r\nLine 2")

        # Check line 0
        assert buf.get_line(0) == "Line 1"
        assert buf.get_line(1) == "Line 2"

        # Check get_char
        char_0_0 = buf.get_char(0, 0)
        assert char_0_0 is not None
        assert char_0_0.data == "L"

        char_out_of_bounds = buf.get_char(999, 999)
        assert char_out_of_bounds is None

        with pytest.raises(IndexError):
            buf.get_line(50)

    def test_resize_screen(self) -> None:
        buf = TerminalBuffer(columns=80, lines=24)
        v0 = buf.version
        buf.resize(100, 30)
        assert buf.columns == 100
        assert buf.lines == 30
        assert buf.version == v0 + 1

        # Resizing to exact same size should be a no-op
        v1 = buf.version
        buf.resize(100, 30)
        assert buf.version == v1

    def test_clear_buffer(self) -> None:
        buf = TerminalBuffer(columns=80, lines=24)
        buf.feed("Some active terminal text")
        assert buf.has_content is True
        v = buf.version

        buf.clear()
        assert buf.has_content is False
        assert buf.version == v + 1
        assert all(line == "" for line in buf.get_visible_lines())


class TestVersionAndContentChecks:
    """Test instant O(1) version counter and visible content presence detection."""

    def test_version_increments_on_feed(self) -> None:
        buf = TerminalBuffer()
        assert buf.version == 0
        buf.feed("a")
        assert buf.version == 1
        buf.feed(b"b")
        assert buf.version == 2

    def test_has_content_ignores_whitespace_and_ansi_controls(self) -> None:
        buf = TerminalBuffer()
        assert buf.has_content is False

        # Feeding whitespace should NOT trigger has_content
        buf.feed("   \r\n\t  ")
        assert buf.has_content is False

        # Feeding pure ANSI color/cursor escape codes should NOT trigger has_content
        buf.feed("\x1b[31m\x1b[1m\x1b[0m\x1b[?25h\x1b[2K")
        assert buf.has_content is False

        # Feeding visible text MUST trigger has_content
        buf.feed("\x1b[32mActive Output\x1b[0m")
        assert buf.has_content is True

    def test_refresh_has_content(self) -> None:
        buf = TerminalBuffer()
        assert buf.refresh_has_content() is False
        buf.feed("Visible content")
        assert buf.refresh_has_content() is True
        buf.clear()
        assert buf.refresh_has_content() is False


class TestRunLengthEncodingAndStyleCaching:
    """Test RLE batching of matching styles, Style object caching, and render retention."""

    def test_rle_batches_adjacent_matching_characters(self) -> None:
        buf = TerminalBuffer(columns=40, lines=5)
        # 20 green chars, then 10 red chars
        buf.feed("\x1b[32m" + "A" * 20 + "\x1b[31m" + "B" * 10 + "\x1b[0m")
        rich_text = buf.get_rich_text(show_cursor=False)

        # Spans must be consolidated into runs, not 30 individual spans
        # Typically 2 styled spans: one for A*20, one for B*10
        assert len(rich_text.spans) == 2
        span1 = rich_text.spans[0]
        span2 = rich_text.spans[1]
        assert span1.end - span1.start == 20
        assert span2.end - span2.start == 10
        assert rich_text.plain.startswith("A" * 20 + "B" * 10)

    def test_style_cache_reuses_instances(self) -> None:
        buf = TerminalBuffer()
        initial_cache_size = len(_STYLE_CACHE)

        buf.feed("\x1b[1;34mBold Blue Text\x1b[0m")
        text1 = buf.get_rich_text()
        size_after_first = len(_STYLE_CACHE)
        assert size_after_first >= initial_cache_size

        # Render again with same styles; no new Style objects should be allocated in cache
        buf.feed("\x1b[1;34mAnother Bold Blue Line\x1b[0m")
        text2 = buf.get_rich_text()
        assert len(_STYLE_CACHE) == size_after_first

    def test_render_retention_avoids_rebuilding_unchanged_frame(self) -> None:
        """Verify that unchanged buffer returns cached render in O(1)."""
        buf = TerminalBuffer(columns=40, lines=5)
        buf.feed("Static terminal text")

        text1 = buf.get_rich_text(show_cursor=True)
        text2 = buf.get_rich_text(show_cursor=True)

        # Content should be identical
        assert text1.plain == text2.plain
        # And cache hit should be fast with same spans
        assert len(text1.spans) == len(text2.spans)

    def test_truecolor_and_256_color_resolution(self) -> None:
        buf = TerminalBuffer(columns=40, lines=5)
        # 256 color code and TrueColor 24-bit RGB
        buf.feed("\x1b[38;5;196mRed256\x1b[0m \x1b[38;2;100;150;200mTrueColor\x1b[0m")
        rich_text = buf.get_rich_text()
        assert "Red256 TrueColor" in rich_text.plain

    def test_resolve_color_helper(self) -> None:
        assert _resolve_color(None) is None
        assert _resolve_color("default") is None
        assert _resolve_color("red") == "red"
        assert _resolve_color("brown") == "yellow"
        assert _resolve_color("brightcyan") == "bright_cyan"
        assert _resolve_color("ff00aa") == "#ff00aa"
        assert _resolve_color("#112233") == "#112233"
        assert _resolve_color(196) == "color(196)"


class TestMCPCleanTextExport:
    """Test ANSI-free clean plain-text export functions for MCP tools."""

    def test_strip_ansi_function(self) -> None:
        raw = "\x1b]0;Term Title\x07\x1b[31;1mError: \x1b[0m\x1b[32mSuccess\x1b[0m\r\n"
        clean = strip_ansi(raw)
        assert clean == "Error: Success\r\n"
        assert "\x1b" not in clean

    def test_get_screen_text_combines_history_and_display_cleanly(self) -> None:
        buf = TerminalBuffer(columns=40, lines=3, history_size=10)
        # Feed 5 lines; 2 lines push into scrollback history, 3 remain visible
        buf.feed("\x1b[31mLine 1\x1b[0m\r\nLine 2\r\n\x1b[32mLine 3\x1b[0m\r\nLine 4\r\nLine 5\r\n")

        screen_text = buf.get_screen_text(lines=10)
        assert "\x1b" not in screen_text
        assert "Line 1" in screen_text
        assert "Line 2" in screen_text
        assert "Line 3" in screen_text
        assert "Line 4" in screen_text
        assert "Line 5" in screen_text

        # Test line limitation
        recent_2 = buf.get_screen_text(lines=2)
        assert "Line 5" in recent_2
        assert "Line 1" not in recent_2

    def test_get_plain_text_and_export_clean_text(self) -> None:
        buf = TerminalBuffer(columns=40, lines=5)
        buf.feed("\x1b[1;33mTask Progress: 100%\x1b[0m\r\nDone.\r\n")

        clean_export = buf.export_clean_text(lines=10)
        assert "Task Progress: 100%" in clean_export
        assert "Done." in clean_export
        assert "\x1b" not in clean_export

        # Visible only (no history)
        visible_plain = buf.get_plain_text(include_history=False)
        assert "Task Progress: 100%" in visible_plain

    def test_get_history_lines(self) -> None:
        buf = TerminalBuffer(columns=40, lines=5, history_size=10)
        buf.feed("H1\r\nH2\r\nH3\r\nH4\r\nH5\r\nH6\r\nVisible1\r\nVisible2\r\n")

        hist = buf.get_history_lines()
        assert len(hist) > 0
        assert "H1" in hist[0]


class TestConcurrencyAndThreadSafety:
    """Test thread-safe concurrent feeds and reads."""

    def test_concurrent_feed_and_render(self) -> None:
        buf = TerminalBuffer(columns=80, lines=24)
        errors: list[Exception] = []

        def feeder() -> None:
            try:
                for i in range(100):
                    buf.feed(f"\x1b[3{i % 8}mWorker chunk {i}\x1b[0m\r\n")
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(50):
                    _ = buf.get_rich_text()
                    _ = buf.get_screen_text(lines=20)
                    _ = buf.has_content
                    _ = buf.version
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=feeder),
            threading.Thread(target=feeder),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Encountered concurrency errors: {errors}"
        assert buf.has_content is True
        assert buf.version >= 200
