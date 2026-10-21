"""Thread-safe virtual terminal buffer using pyte and Rich.

Maintains a 2D character matrix, scrollback history, and ANSI state,
allowing both rendered Rich Text with Run-Length Encoding (RLE) and Style caching
for Textual UI display, and pristine ANSI-free clean text export for MCP tool inspection.
"""

from __future__ import annotations

import collections
import re
import threading
from typing import Sequence

import pyte
from rich.style import Style
from rich.text import Text


# Regular expression matching ANSI escape sequences:
# 1. OSC sequences: \x1b] ... (\x07 | \x1b\)
# 2. CSI sequences: \x1b[ ... [@-~]
# 3. 2-character escape sequences: \x1b[@-Z\\-_]
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:"
    r"\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\[[0-?]*[ -/]*[@-~]"
    r"|[@-Z\\-_]"
    r")"
)


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences, control sequences, and OSC commands from text.

    Returns clean plain text suitable for MCP tools and logs.
    """
    return _ANSI_ESCAPE_RE.sub("", text)


def _contains_visible_content(text: str) -> bool:
    """Fast check whether text contains visible printable characters outside ANSI escapes."""
    clean = _ANSI_ESCAPE_RE.sub("", text)
    return any(not c.isspace() for c in clean)


# Mapping pyte color names to Rich color equivalents
_PYTE_COLOR_MAP: dict[str, str] = {
    "black": "black",
    "red": "red",
    "green": "green",
    "brown": "yellow",  # pyte uses 'brown' for standard ANSI yellow
    "yellow": "yellow",
    "blue": "blue",
    "magenta": "magenta",
    "cyan": "cyan",
    "white": "white",
    "brightblack": "bright_black",
    "brightred": "bright_red",
    "brightgreen": "bright_green",
    "brightbrown": "bright_yellow",
    "brightyellow": "bright_yellow",
    "brightblue": "bright_blue",
    "brightmagenta": "bright_magenta",
    "brightcyan": "bright_cyan",
    "brightwhite": "bright_white",
}

_STYLE_CACHE: dict[tuple, Style] = {}
_MAX_STYLE_CACHE_SIZE = 2048
_DEFAULT_STYLE_KEY = (None, None, False, False, False, False, False, False)


def _get_cached_style(key: tuple) -> Style | None:
    """Retrieve or build a cached Rich Style instance to avoid object allocation in hot loop."""
    if key == _DEFAULT_STYLE_KEY:
        return None
    style = _STYLE_CACHE.get(key)
    if style is None:
        fg, bg, bold, italics, underline, strike, reverse, blink = key
        style = Style(
            color=fg,
            bgcolor=bg,
            bold=bold,
            italic=italics,
            underline=underline,
            strike=strike,
            reverse=reverse,
            blink=blink,
        )
        if len(_STYLE_CACHE) >= _MAX_STYLE_CACHE_SIZE:
            # Evict oldest entry (FIFO) to prevent unbounded memory growth
            _STYLE_CACHE.pop(next(iter(_STYLE_CACHE)))
        _STYLE_CACHE[key] = style
    return style


def _resolve_color(color_val: str | int | None) -> str | None:
    """Resolve a pyte color value into a valid Rich color identifier."""
    if color_val is None or color_val == "default":
        return None
    if isinstance(color_val, str):
        lowered = color_val.lower().strip()
        if lowered in _PYTE_COLOR_MAP:
            return _PYTE_COLOR_MAP[lowered]
        if lowered.startswith("#"):
            return lowered
        if len(lowered) in (3, 6, 8) and all(c in "0123456789abcdef" for c in lowered):
            return f"#{lowered}"
        return lowered
    if isinstance(color_val, int):
        if 0 <= color_val <= 255:
            return f"color({color_val})"
        return str(color_val)
    return str(color_val)


class TerminalBuffer:
    """Thread-safe virtual terminal screen and history buffer.

    Wraps a pyte.HistoryScreen to maintain an accurate 2D display grid,
    ANSI attributes, and a rolling scrollback buffer. Features:
    - 2D character matrix emulation with pyte.HistoryScreen.
    - Run-Length Encoding (RLE) grouping contiguous characters with matching styles.
    - Rich Style object caching to prevent memory bloat and garbage collection pauses.
    - Frame-level render caching to avoid re-rendering unchanged content ("تفادي إعادة رسم ما لم يتغير").
    - O(1) buffer version tracking (`version counter`) and content presence detection (`has_content`).
    - Clean ANSI-free plain text export functions for MCP tools.
    """

    def __init__(
        self,
        columns: int = 80,
        lines: int = 24,
        history_size: int = 1000,
    ) -> None:
        self._columns = max(20, columns)
        self._lines = max(5, lines)
        self._history_size = max(10, history_size)

        self._lock = threading.RLock()
        self._screen = pyte.HistoryScreen(
            self._columns,
            self._lines,
            history=self._history_size,
        )
        self._stream = pyte.Stream(self._screen)
        self._recent_logs: collections.deque[str] = collections.deque(maxlen=self._history_size)
        self._version: int = 0
        self._has_content: bool = False

        # Render & text caches for maximum performance
        self._cached_rich_text: Text | None = None
        self._cached_rich_key: tuple[int, int, int, bool] | None = None
        self._cached_screen_text: str | None = None
        self._cached_screen_text_key: tuple[int, int] | None = None
        self._cached_visible_lines: list[str] | None = None
        self._cached_visible_lines_version: int = -1

    def _invalidate_caches(self) -> None:
        """Invalidate rendered Rich Text and text export caches."""
        self._cached_rich_text = None
        self._cached_rich_key = None
        self._cached_screen_text = None
        self._cached_screen_text_key = None
        self._cached_visible_lines = None
        self._cached_visible_lines_version = -1

    @property
    def has_content(self) -> bool:
        """Instant O(1) check if buffer has received any visible display output."""
        return self._has_content

    @property
    def version(self) -> int:
        """Instant O(1) incrementing version counter to detect buffer modifications."""
        return self._version

    @property
    def columns(self) -> int:
        """Visible screen column width."""
        return self._columns

    @property
    def lines(self) -> int:
        """Visible screen row height."""
        return self._lines

    @property
    def history_size(self) -> int:
        """Maximum scrollback history lines configured."""
        return self._history_size

    @property
    def cursor(self) -> tuple[int, int]:
        """Current cursor position as (y, x) 0-indexed coordinates."""
        with self._lock:
            return (self._screen.cursor.y, self._screen.cursor.x)

    @property
    def raw_logs(self) -> list[str]:
        """Return raw log chunks received by the buffer."""
        with self._lock:
            return list(self._recent_logs)

    @property
    def display(self) -> list[str]:
        """Return current visible 2D grid as a list of strings."""
        return self.get_visible_lines()

    def get_char(self, x: int, y: int) -> pyte.screens.Char | None:
        """Return the character cell object at 2D grid coordinate (x, y)."""
        with self._lock:
            if 0 <= y < self._lines and 0 <= x < self._columns:
                return self._screen.buffer[y][x]
            return None

    def get_line(self, y: int) -> str:
        """Return the clean text of row y in the visible 2D grid."""
        with self._lock:
            if 0 <= y < self._lines:
                return self._screen.display[y].rstrip()
            raise IndexError(f"Row index {y} out of range (0..{self._lines - 1})")

    def feed(self, data: str | bytes) -> None:
        """Feed raw output from the PTY into the virtual terminal emulator.

        Updates the 2D grid, increments version counter, and detects content in O(1).
        """
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = data

        with self._lock:
            self._stream.feed(text)
            self._recent_logs.append(text)
            self._version += 1
            self._invalidate_caches()

            if not self._has_content and _contains_visible_content(text):
                self._has_content = True

    def resize(self, columns: int, lines: int) -> None:
        """Resize the virtual terminal screen dimensions."""
        columns = max(20, columns)
        lines = max(5, lines)
        with self._lock:
            if columns == self._columns and lines == self._lines:
                return
            self._columns = columns
            self._lines = lines
            self._screen.resize(lines=lines, columns=columns)
            self._version += 1
            self._invalidate_caches()

    def clear(self) -> None:
        """Reset the virtual terminal screen, history, and content state."""
        with self._lock:
            self._screen.reset()
            self._recent_logs.clear()
            self._version += 1
            self._has_content = False
            self._invalidate_caches()

    def refresh_has_content(self) -> bool:
        """Re-scan visible grid and scrollback history to update has_content state."""
        with self._lock:
            has_display = any(line.strip() for line in self._screen.display)
            has_history = False
            history_rows = getattr(self._screen.history, "top", None)
            if history_rows:
                has_history = any(
                    any(char.data.strip() for char in row.values()) for row in history_rows
                )
            self._has_content = has_display or has_history
            return self._has_content

    def get_visible_lines(self) -> list[str]:
        """Return visible screen rows as clean text strings (trailing spaces trimmed).

        Result is cached per buffer version to avoid redundant parsing.
        """
        with self._lock:
            if (
                self._cached_visible_lines is not None
                and self._cached_visible_lines_version == self._version
            ):
                return list(self._cached_visible_lines)

            lines = [line.rstrip() for line in self._screen.display]
            self._cached_visible_lines = lines
            self._cached_visible_lines_version = self._version
            return list(lines)

    def get_history_lines(self, max_lines: int | None = None) -> list[str]:
        """Return scrollback history rows as clean plain text strings."""
        with self._lock:
            lines: list[str] = []
            history_rows = getattr(self._screen.history, "top", None)
            if history_rows:
                for row_dict in history_rows:
                    if not row_dict:
                        lines.append("")
                        continue
                    max_col = max(row_dict.keys()) + 1
                    row_str = "".join(
                        row_dict[x].data if x in row_dict else " " for x in range(max_col)
                    )
                    lines.append(row_str.rstrip())

            if max_lines is not None and max_lines > 0 and len(lines) > max_lines:
                lines = lines[-max_lines:]

            return lines

    def get_screen_text(self, lines: int = 50) -> str:
        """Return up to `lines` recent lines combining scrollback history and visible display.

        Clean, ANSI-free plain text ideal for MCP inspection tools.
        Cached by (version, lines) for instant O(1) retrieval when unchanged.
        """
        with self._lock:
            if (
                self._cached_screen_text is not None
                and self._cached_screen_text_key == (self._version, lines)
            ):
                return self._cached_screen_text

            all_lines: list[str] = []

            # 1. Collect history lines if available
            history_rows = getattr(self._screen.history, "top", None)
            if history_rows:
                for row_dict in history_rows:
                    if not row_dict:
                        all_lines.append("")
                        continue
                    max_col = max(row_dict.keys()) + 1
                    chars = [
                        row_dict[x].data if x in row_dict else " " for x in range(max_col)
                    ]
                    all_lines.append("".join(chars).rstrip())

            # 2. Collect current display lines
            for row_str in self._screen.display:
                all_lines.append(row_str.rstrip())

            # Filter out consecutive trailing empty lines
            while all_lines and not all_lines[-1]:
                all_lines.pop()

            if lines > 0 and len(all_lines) > lines:
                all_lines = all_lines[-lines:]

            result = "\n".join(all_lines)
            self._cached_screen_text = result
            self._cached_screen_text_key = (self._version, lines)
            return result

    def get_plain_text(self, include_history: bool = True, max_lines: int | None = None) -> str:
        """Export clean, ANSI-free text from the buffer for MCP tools and logging."""
        lines_arg = max_lines if (max_lines is not None and max_lines > 0) else 0
        if not include_history:
            with self._lock:
                visible = [line.rstrip() for line in self._screen.display]
                while visible and not visible[-1]:
                    visible.pop()
                if lines_arg > 0 and len(visible) > lines_arg:
                    visible = visible[-lines_arg:]
                return "\n".join(visible)
        return self.get_screen_text(lines=lines_arg)

    def export_clean_text(self, lines: int = 50, include_history: bool = True) -> str:
        """Clean plain text export function explicitly provided for MCP tool consumption."""
        return self.get_plain_text(include_history=include_history, max_lines=lines)

    def get_rich_text(self, show_cursor: bool = True) -> Text:
        """Render the 2D screen buffer into a Rich Text object with full ANSI styles.

        Optimized with Run-Length Encoding (RLE) character batching, Style object caching,
        and frame-level cache retention to prevent memory bloat and avoid re-rendering
        unchanged content ("تفادي إعادة رسم ما لم يتغير").
        """
        with self._lock:
            cursor_y = self._screen.cursor.y
            cursor_x = self._screen.cursor.x
            cache_key = (self._version, cursor_y, cursor_x, show_cursor)

            # Return cached Text if version and cursor state have not changed
            if self._cached_rich_text is not None and self._cached_rich_key == cache_key:
                return self._cached_rich_text.copy()

            rich_text = Text()

            for y in range(self._lines):
                row = self._screen.buffer[y]

                # Determine last non-empty character to avoid unnecessary trailing spans,
                # while preserving cursor highlight and background color styles
                max_x = self._columns
                for x in range(self._columns - 1, -1, -1):
                    char_obj = row[x]
                    is_cursor = show_cursor and y == cursor_y and x == cursor_x
                    has_data = char_obj.data != " "
                    has_bg = char_obj.bg not in ("default", None)
                    has_special = bool(
                        char_obj.underscore or char_obj.strikethrough or char_obj.reverse
                    )

                    if has_data or is_cursor or has_bg or has_special:
                        max_x = x + 1
                        break
                else:
                    max_x = 1 if (show_cursor and y == cursor_y) else 0

                run_chars: list[str] = []
                current_style: Style | None = None
                current_style_key: tuple | None = None

                for x in range(max_x):
                    char_obj = row[x]
                    data = char_obj.data or " "

                    fg = _resolve_color(char_obj.fg)
                    bg = _resolve_color(char_obj.bg)
                    bold = bool(char_obj.bold)
                    italics = bool(char_obj.italics)
                    underline = bool(char_obj.underscore)
                    strike = bool(char_obj.strikethrough)
                    reverse = bool(char_obj.reverse)
                    blink = bool(char_obj.blink)

                    # Highlight the active cursor position
                    if show_cursor and y == cursor_y and x == cursor_x:
                        reverse = not reverse

                    style_key = (fg, bg, bold, italics, underline, strike, reverse, blink)

                    if style_key != current_style_key:
                        if run_chars:
                            rich_text.append("".join(run_chars), style=current_style)
                            run_chars = []
                        current_style_key = style_key
                        current_style = _get_cached_style(style_key)

                    run_chars.append(data)

                if run_chars:
                    rich_text.append("".join(run_chars), style=current_style)

                if y < self._lines - 1:
                    rich_text.append("\n")

            self._cached_rich_text = rich_text
            self._cached_rich_key = cache_key
            return rich_text.copy()
