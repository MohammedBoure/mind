"""Cross-Platform System Clipboard Integration & Synchronization Engine.

Provides multi-tiered, robust clipboard synchronization across Windows, Linux,
and macOS:
1. Primary: `pyperclip` for direct OS clipboard integration.
2. Secondary: Textual Application Clipboard API (including OSC 52 terminal copy).
3. Tertiary: Native Win32 API via ctypes (Windows Unicode clipboard without external tools).
4. Quaternary: Native POSIX CLI tools (wl-copy/wl-paste on Wayland, xclip/xsel on X11, pbcopy/pbpaste on macOS).
5. Safe Fallback: In-memory persistent clipboard buffer (ensures zero data loss in headless/container environments).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)

# In-memory clipboard store for fallback and internal history
_IN_MEMORY_CLIPBOARD: str = ""
_CLIPBOARD_HISTORY: list[str] = []
_MAX_HISTORY_ITEMS = 20


# ── Win32 Native Fallback via ctypes ──────────────────────────────────────────

def _copy_win32_native(text: str) -> bool:
    """Copy text using direct Win32 Unicode clipboard API."""
    if sys.platform != "win32":
        return False

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    # Attempt opening clipboard with brief retry in case another process locked it
    opened = False
    for _ in range(5):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.02)

    if not opened:
        return False

    try:
        user32.EmptyClipboard()
        # Allocate movable global memory for null-terminated UTF-16 string
        encoded = text.encode("utf-16le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False

        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False

        try:
            ctypes.memmove(ptr, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(h_mem)

        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            kernel32.GlobalFree(h_mem)
            return False

        return True
    finally:
        user32.CloseClipboard()


def _paste_win32_native() -> str:
    """Retrieve text from Win32 Unicode clipboard API."""
    if sys.platform != "win32":
        return ""

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    CF_UNICODETEXT = 13

    if not user32.OpenClipboard(None):
        return ""

    try:
        h_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_mem:
            return ""

        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            return ""

        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h_mem)
    finally:
        user32.CloseClipboard()


# ── POSIX CLI Fallbacks (wl-copy, xclip, xsel, pbcopy) ────────────────────────

def _copy_posix_cli(text: str) -> bool:
    """Copy text using system CLI utilities on Linux/Unix/macOS."""
    # macOS
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=1.0)
            return True
        except Exception:
            pass

    # Wayland
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        try:
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True, timeout=1.0)
            return True
        except Exception:
            pass

    # X11 xclip
    if shutil.which("xclip"):
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"),
                check=True,
                timeout=1.0,
            )
            return True
        except Exception:
            pass

    # X11 xsel
    if shutil.which("xsel"):
        try:
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text.encode("utf-8"),
                check=True,
                timeout=1.0,
            )
            return True
        except Exception:
            pass

    return False


def _paste_posix_cli() -> str:
    """Paste text using system CLI utilities on Linux/Unix/macOS."""
    # macOS
    if sys.platform == "darwin" and shutil.which("pbpaste"):
        try:
            res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass

    # Wayland
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        try:
            res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass

    # X11 xclip
    if shutil.which("xclip"):
        try:
            res = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass

    # X11 xsel
    if shutil.which("xsel"):
        try:
            res = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass

    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def sanitize_clipboard_text(text: str) -> str:
    """Clean rogue dead keys, Windows scancode leftovers, and normalize line endings."""
    if not text:
        return ""
    # Strip leading stray \xe0 bytes on Windows
    cleaned = text.lstrip("\xe0")
    # Normalize Windows line endings to \n
    cleaned = cleaned.replace("\r\n", "\n")
    return cleaned


def copy_to_clipboard(text: str, app: Any = None) -> bool:
    """Copy text to system clipboard via multi-tiered fallback pipeline.

    Order of attempts:
    1. pyperclip
    2. Textual App.copy_to_clipboard (OSC 52)
    3. Native Win32 API (on Windows)
    4. POSIX CLI tools (wl-copy, xclip, xsel, pbcopy)
    5. In-Memory internal buffer (always succeeds)

    Returns True if text was successfully copied to at least one mechanism.
    """
    global _IN_MEMORY_CLIPBOARD
    if not text:
        return False

    # Store in memory buffer and history immediately
    _IN_MEMORY_CLIPBOARD = text
    if not _CLIPBOARD_HISTORY or _CLIPBOARD_HISTORY[-1] != text:
        _CLIPBOARD_HISTORY.append(text)
        if len(_CLIPBOARD_HISTORY) > _MAX_HISTORY_ITEMS:
            _CLIPBOARD_HISTORY.pop(0)

    success = False

    # 1. Try pyperclip
    try:
        import pyperclip
        pyperclip.copy(text)
        success = True
    except Exception as e:
        logger.debug(f"pyperclip.copy failed: {e}")

    # 2. Try Textual App copy_to_clipboard (supports OSC 52 terminal copy)
    if app is not None and hasattr(app, "copy_to_clipboard"):
        try:
            app.copy_to_clipboard(text)
            success = True
        except Exception as e:
            logger.debug(f"app.copy_to_clipboard failed: {e}")

    # 3. Try Native Win32 API on Windows
    if not success and sys.platform == "win32":
        try:
            if _copy_win32_native(text):
                success = True
        except Exception as e:
            logger.debug(f"win32 native copy failed: {e}")

    # 4. Try POSIX CLI tools on Linux / macOS
    if not success and sys.platform != "win32":
        try:
            if _copy_posix_cli(text):
                success = True
        except Exception as e:
            logger.debug(f"posix cli copy failed: {e}")

    # 5. In-memory fallback always guarantees internal copy success
    return True


def get_clipboard_text(app: Any = None) -> str:
    """Retrieve text from system clipboard using multi-tiered fallback pipeline.

    Order of attempts:
    1. pyperclip.paste()
    2. Native Win32 API (on Windows)
    3. POSIX CLI tools (wl-paste, xclip, xsel, pbpaste)
    4. In-Memory fallback buffer
    """
    global _IN_MEMORY_CLIPBOARD

    # 1. Try pyperclip
    try:
        import pyperclip
        val = pyperclip.paste()
        if val:
            return sanitize_clipboard_text(val)
    except Exception as e:
        logger.debug(f"pyperclip.paste failed: {e}")

    # 2. Try Native Win32 API on Windows
    if sys.platform == "win32":
        try:
            val = _paste_win32_native()
            if val:
                return sanitize_clipboard_text(val)
        except Exception as e:
            logger.debug(f"win32 native paste failed: {e}")

    # 3. Try POSIX CLI tools on Linux / macOS
    if sys.platform != "win32":
        try:
            val = _paste_posix_cli()
            if val:
                return sanitize_clipboard_text(val)
        except Exception as e:
            logger.debug(f"posix cli paste failed: {e}")

    # 4. In-memory fallback
    return sanitize_clipboard_text(_IN_MEMORY_CLIPBOARD)


def get_clipboard_history() -> list[str]:
    """Return recent clipboard copies history in this session."""
    return list(_CLIPBOARD_HISTORY)


def clear_clipboard() -> bool:
    """Clear clipboard contents across available backends."""
    global _IN_MEMORY_CLIPBOARD
    _IN_MEMORY_CLIPBOARD = ""

    success = False
    try:
        import pyperclip
        pyperclip.copy("")
        success = True
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    success = True
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass

    return success or True
