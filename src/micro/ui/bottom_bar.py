"""Bottom bar widget displaying keybind hints."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static


# Keybind hints shown in the bottom bar
_KEYBINDS: list[tuple[str, str]] = [
    ("q", "Quit"),
    ("n", "New Tab"),
    ("Tab", "Focus"),
    ("m", "Mock Interrupt"),
    ("s", "Split"),
    ("?", "Help"),
]


class BottomBar(Widget):
    """Bottom status bar showing available keyboard shortcuts."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="bottom-bar"):
            for key, desc in _KEYBINDS:
                yield Static(
                    f"[bold cyan]{key}[/]: {desc}",
                    classes="keybind-hint",
                )
