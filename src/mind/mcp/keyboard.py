"""High-Performance AI Keyboard Controller and MCP Integration Module.

Exposes human-like typing with realistic cadence, keystroke jitter, full native
support for Arabic and Unicode text via Linux X11 clipboard/xdotool injection,
key pressing, and hotkey combination dispatch with headless simulation fallbacks.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

logger = logging.getLogger("mind.mcp.keyboard")

# Normalized key translation table for xdotool / X11 keysyms
KEY_TRANSLATIONS: dict[str, str] = {
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "esc": "Escape",
    "escape": "Escape",
    "backspace": "BackSpace",
    "bs": "BackSpace",
    "space": "space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Page_Up",
    "page_up": "Page_Up",
    "pagedown": "Page_Down",
    "page_down": "Page_Down",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super",
    "win": "super",
    "meta": "super",
    "cmd": "super",
}

for i in range(1, 13):
    KEY_TRANSLATIONS[f"f{i}"] = f"F{i}"


def find_xdotool() -> str | None:
    """Locate the xdotool executable on the system."""
    for candidate in [
        os.environ.get("XDOTOOL_PATH", ""),
        "/home/pluto/.local/bin/xdotool",
        "/usr/bin/xdotool",
        shutil.which("xdotool") or "",
    ]:
        if candidate and os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def find_xclip() -> str | None:
    """Locate the xclip executable on the system."""
    for candidate in [
        os.environ.get("XCLIP_PATH", ""),
        "/usr/bin/xclip",
        shutil.which("xclip") or "",
    ]:
        if candidate and os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def ensure_display_environment() -> str | None:
    """Ensure Linux display environment variable is configured if an X11 socket exists."""
    if not sys.platform.startswith("linux"):
        return os.environ.get("DISPLAY")

    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if display:
        return display

    for display_num in range(4):
        socket_path = f"/tmp/.X11-unix/X{display_num}"
        if os.path.exists(socket_path):
            auto_display = f":{display_num}"
            os.environ["DISPLAY"] = auto_display
            logger.debug("Auto-configured Linux DISPLAY to %s", auto_display)
            return auto_display

    return None


def is_headless_environment() -> bool:
    """Detect whether current execution environment is running without an active display server."""
    disp = ensure_display_environment()
    if sys.platform.startswith("linux"):
        if not disp:
            return True
        xdotool_path = find_xdotool()
        if xdotool_path:
            try:
                res = subprocess.run(
                    [xdotool_path, "getmouselocation"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                if res.returncode == 0:
                    return False
            except Exception:
                pass
        return not bool(disp)
    return False


def normalize_key_name(key: str) -> str:
    """Normalize user key names into standard X11 keysym identifiers."""
    cleaned = key.strip().lower()
    return KEY_TRANSLATIONS.get(cleaned, key.strip())


class KeyboardController:
    """High-level Keyboard Controller supporting natural human typing, hotkeys, and Arabic/Unicode."""

    def __init__(self, dry_run: bool | None = None) -> None:
        ensure_display_environment()
        self.xdotool_path = find_xdotool()
        self.xclip_path = find_xclip()
        self.headless = is_headless_environment()

        if dry_run is not None:
            self.dry_run = dry_run
        else:
            self.dry_run = self.headless or (self.xdotool_path is None)

    async def type_text(
        self,
        text: str,
        wpm: int = 75,
        natural_delay: bool = True,
    ) -> dict[str, Any]:
        """Type text with authentic human cadence, keystroke jitter, and seamless Arabic/Unicode support.

        Args:
            text: Text string to type.
            wpm: Typing speed in words per minute (standard 5 chars/word, typical 60-90 WPM).
            natural_delay: Whether to introduce authentic human neuromuscular jitter between keystrokes.

        Returns:
            Telemetry dictionary with character count, WPM, duration, and execution status.
        """
        # Character mapping rule: Replace Arabic character "٩" (U+0669) with Arabic letter "ج"
        processed_text = text.replace("\u0669", "ج")

        if not processed_text:
            return {
                "status": "success",
                "action": "keyboard_type",
                "characters_count": 0,
                "wpm": wpm,
                "natural_delay": natural_delay,
                "estimated_duration_ms": 0.0,
                "dry_run": self.dry_run,
                "mode": "headless_simulation" if self.dry_run else "live_execution",
            }

        # Human typing cadence calculation:
        # Standard: 1 word = 5 characters -> char_rate = (wpm * 5) / 60 chars/second
        effective_wpm = max(20, min(180, int(wpm)))
        base_char_delay = 60.0 / (effective_wpm * 5.0)  # e.g., 0.16s for 75 WPM

        is_unicode = any(ord(c) > 127 for c in processed_text)
        delays: list[float] = []

        for ch in processed_text:
            if natural_delay:
                # Keystroke jitter: ~0.7x to 1.3x base delay
                jitter = random.uniform(0.7, 1.3)
                ch_delay = base_char_delay * jitter
                # Cognitive word/sentence boundary pauses
                if ch in (" ", "\t"):
                    ch_delay += random.uniform(0.04, 0.10)
                elif ch in (".", ",", "!", "?", "\n"):
                    ch_delay += random.uniform(0.08, 0.18)
                ch_delay = max(0.035, min(0.35, ch_delay))
            else:
                ch_delay = base_char_delay if natural_delay is not None else 0.012

            delays.append(ch_delay)

        total_delay_s = sum(delays)
        total_delay_ms = total_delay_s * 1000.0

        if not self.dry_run:
            def _live_type():
                # If Unicode / Arabic text is present, inject via UTF-8 clipboard + ctrl+v for 100% fidelity
                if is_unicode and self.xclip_path and self.xdotool_path:
                    try:
                        p = subprocess.Popen(
                            [self.xclip_path, "-selection", "clipboard", "-t", "UTF8_STRING"],
                            stdin=subprocess.PIPE,
                        )
                        p.communicate(input=processed_text.encode("utf-8"))
                        # Small settling delay before paste
                        time.sleep(0.05)
                        subprocess.run(
                            [self.xdotool_path, "key", "--clearmodifiers", "ctrl+v"],
                            check=False,
                        )
                        if natural_delay:
                            time.sleep(min(1.5, total_delay_s * 0.4))
                        return
                    except Exception as exc:
                        logger.debug("Clipboard injection failed, falling back to xdotool type: %s", exc)

                # Character-by-character live typing with human cadence jitter
                if self.xdotool_path:
                    if natural_delay and len(processed_text) <= 120:
                        for ch, d in zip(processed_text, delays):
                            subprocess.run(
                                [self.xdotool_path, "type", "--clearmodifiers", "--delay", "10", ch],
                                check=False,
                            )
                            time.sleep(d)
                    else:
                        delay_ms = max(10, min(120, int(round(base_char_delay * 1000.0))))
                        subprocess.run(
                            [self.xdotool_path, "type", "--clearmodifiers", "--delay", str(delay_ms), processed_text],
                            check=False,
                        )

            await asyncio.to_thread(_live_type)

        return {
            "status": "success",
            "action": "keyboard_type",
            "text": processed_text,
            "characters_count": len(processed_text),
            "wpm": effective_wpm,
            "natural_delay": natural_delay,
            "estimated_duration_ms": round(total_delay_ms, 2),
            "is_unicode": is_unicode,
            "dry_run": self.dry_run,
            "mode": "headless_simulation" if self.dry_run else "live_execution",
        }

    async def press_key(self, key: str) -> dict[str, Any]:
        """Press an individual key (e.g. 'Return', 'Tab', 'Escape', 'BackSpace', 'space', 'Up', 'Down')."""
        if not key or not key.strip():
            return {"status": "error", "message": "Key name cannot be empty."}

        norm_key = normalize_key_name(key)

        if not self.dry_run and self.xdotool_path:
            def _live_press():
                subprocess.run(
                    [self.xdotool_path, "key", "--clearmodifiers", norm_key],
                    check=False,
                )
            await asyncio.to_thread(_live_press)

        return {
            "status": "success",
            "action": "keyboard_press",
            "key": key,
            "normalized_key": norm_key,
            "dry_run": self.dry_run,
            "mode": "headless_simulation" if self.dry_run else "live_execution",
        }

    async def hotkey(self, keys: Sequence[str]) -> dict[str, Any]:
        """Trigger a hotkey combination (e.g. ['ctrl', 'c'], ['alt', 'tab'], ['ctrl', 'shift', 't'])."""
        if not keys:
            return {"status": "error", "message": "Keys list cannot be empty."}

        normalized_parts = [normalize_key_name(k) for k in keys if k.strip()]
        if not normalized_parts:
            return {"status": "error", "message": "No valid keys in hotkey sequence."}

        combo = "+".join(normalized_parts)

        if not self.dry_run and self.xdotool_path:
            def _live_hotkey():
                subprocess.run(
                    [self.xdotool_path, "key", "--clearmodifiers", combo],
                    check=False,
                )
            await asyncio.to_thread(_live_hotkey)

        return {
            "status": "success",
            "action": "keyboard_hotkey",
            "keys": list(keys),
            "combo": combo,
            "dry_run": self.dry_run,
            "mode": "headless_simulation" if self.dry_run else "live_execution",
        }


# Global singleton controller
_keyboard_controller: KeyboardController | None = None


def get_keyboard_controller() -> KeyboardController:
    """Retrieve or initialize the global KeyboardController singleton."""
    global _keyboard_controller
    if _keyboard_controller is None:
        _keyboard_controller = KeyboardController()
    return _keyboard_controller


def reset_keyboard_controller() -> None:
    """Reset the global KeyboardController instance (for testing)."""
    global _keyboard_controller
    _keyboard_controller = None
