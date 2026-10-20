"""System clipboard integration for mind TUI.

Provides cross-platform clipboard synchronization using pyperclip with fallback
to Textual app.copy_to_clipboard.
"""

from __future__ import annotations

from typing import Any


def copy_to_clipboard(text: str, app: Any = None) -> bool:
    """Copy text to system clipboard.

    Tries pyperclip first for direct OS clipboard access, and Textual's
    built-in copy_to_clipboard as a fallback.

    Returns True if successfully copied.
    """
    if not text:
        return False

    success = False

    # 1. Try pyperclip
    try:
        import pyperclip
        pyperclip.copy(text)
        success = True
    except Exception:
        pass

    # 2. Try Textual App copy_to_clipboard
    if app is not None and hasattr(app, "copy_to_clipboard"):
        try:
            app.copy_to_clipboard(text)
            success = True
        except Exception:
            pass

    return success


def get_clipboard_text() -> str:
    """Retrieve text from system clipboard if available."""
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        return ""
