"""Thread-safe virtual terminal buffer using pyte and Rich.

Maintains a 2D character matrix, scrollback history, and ANSI state,
allowing both rendered Rich Text for Textual UI display and clean text
export for MCP tool inspection.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
import threading
from typing import Sequence

import pyte
from rich.style import Style
from rich.text import Text


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


def _resolve_color(color_val: str | int | None) -> str | None:
    """Resolve a pyte color value into a valid Rich color identifier."""
    if color_val is None or color_val == "default":
        return None
    if isinstance(color_val, str):
        lowered = color_val.lower()
        if lowered in _PYTE_COLOR_MAP:
            return _PYTE_COLOR_MAP[lowered]
        if lowered.startswith("#") or len(lowered) == 6:
            return f"#{lowered.lstrip('#')}"
        return lowered
    if isinstance(color_val, int):
        return f"color({color_val})"
    return str(color_val)


class TerminalBuffer:
    """Thread-safe terminal screen and history buffer.

    Wraps a pyte.HistoryScreen to maintain an accurate 2D display grid,
    ANSI attributes, and a rolling scrollback buffer.
    """

    def __init__(
        self,
        columns: int = 80,
        lines: int = 24,
        history_size: int = 1000,
    ) -> None:
        self._columns = max(20, columns)
        self._lines = max(5, lines)
        self._history_size = history_size

        self._lock = threading.Lock()
        self._screen = pyte.HistoryScreen(
            self._columns,
            self._lines,
            history=self._history_size,
        )
        self._stream = pyte.Stream(self._screen)
        self._recent_logs: collections.deque[str] = collections.deque(maxlen=history_size)
        self._version: int = 0

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def lines(self) -> int:
        return self._lines

    @property
    def version(self) -> int:
        """Incrementing version counter to detect buffer modifications."""
        return self._version

    @property
    def cursor(self) -> tuple[int, int]:
        """Current cursor position as (y, x)."""
        with self._lock:
            return (self._screen.cursor.y, self._screen.cursor.x)

    def feed(self, data: str | bytes) -> None:
        """Feed raw output from the PTY into the virtual terminal emulator."""
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = data

        with self._lock:
            self._stream.feed(text)
            self._recent_logs.append(text)
            self._version += 1

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

    def clear(self) -> None:
        """Reset the virtual terminal screen."""
        with self._lock:
            self._screen.reset()
            self._recent_logs.clear()
            self._version += 1

    def get_visible_lines(self) -> list[str]:
        """Return visible screen rows as clean text strings (trailing spaces trimmed)."""
        with self._lock:
            return [line.rstrip() for line in self._screen.display]

    def get_screen_text(self, lines: int = 50) -> str:
        """Return up to `lines` recent lines combining scrollback history and visible display.

        Ideal for MCP inspection tools.
        """
        with self._lock:
            all_lines: list[str] = []

            # 1. Collect history lines if available
            history_rows = getattr(self._screen.history, "top", None)
            if history_rows:
                for row_dict in history_rows:
                    chars = [row_dict[x].data for x in range(self._columns) if x in row_dict]
                    all_lines.append("".join(chars).rstrip())

            # 2. Collect current display lines
            for row_str in self._screen.display:
                all_lines.append(row_str.rstrip())

            # Filter out consecutive trailing empty lines
            while all_lines and not all_lines[-1]:
                all_lines.pop()

            if lines > 0 and len(all_lines) > lines:
                all_lines = all_lines[-lines:]

            return "\n".join(all_lines)

    def get_rich_text(self, show_cursor: bool = True) -> Text:
        """Render the 2D screen buffer into a Rich Text object with full ANSI styles."""
        with self._lock:
            rich_text = Text()
            cursor_y = self._screen.cursor.y
            cursor_x = self._screen.cursor.x

            for y in range(self._lines):
                row = self._screen.buffer[y]
                # Determine last non-empty character to avoid unnecessary trailing spans
                max_x = self._columns
                for x in range(self._columns - 1, -1, -1):
                    char_obj = row[x]
                    if char_obj.data != " " or (show_cursor and y == cursor_y and x == cursor_x):
                        max_x = x + 1
                        break
                else:
                    max_x = 1 if (show_cursor and y == cursor_y) else 0

                for x in range(max_x):
                    char_obj = row[x]
                    data = char_obj.data or " "

                    fg = _resolve_color(char_obj.fg)
                    bg = _resolve_color(char_obj.bg)
                    bold = bool(char_obj.bold)
                    italics = bool(char_obj.italics)
                    underline = bool(char_obj.underscore)
                    reverse = bool(char_obj.reverse)

                    # Highlight the active cursor position
                    if show_cursor and y == cursor_y and x == cursor_x:
                        reverse = not reverse

                    style = Style(
                        color=fg,
                        bgcolor=bg,
                        bold=bold,
                        italic=italics,
                        underline=underline,
                        reverse=reverse,
                    )
                    rich_text.append(data, style=style)

                if y < self._lines - 1:
                    rich_text.append("\n")

            return rich_text
