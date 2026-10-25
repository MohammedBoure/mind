"""Comprehensive test suite for Keyboard MCP tools and controller."""

from __future__ import annotations

import asyncio
from typing import Any
import pytest

from mind.mcp.keyboard import (
    KeyboardController,
    get_keyboard_controller,
    normalize_key_name,
    reset_keyboard_controller,
)
from mind.mcp.server import create_mcp_server, reset_default_mcp_server


@pytest.fixture(autouse=True)
def clean_state():
    """Ensure clean global controller and MCP server state before and after each test."""
    reset_default_mcp_server()
    reset_keyboard_controller()
    yield
    reset_default_mcp_server()
    reset_keyboard_controller()


def test_normalize_key_name():
    """Verify key normalization mappings."""
    assert normalize_key_name("enter") == "Return"
    assert normalize_key_name("return") == "Return"
    assert normalize_key_name("esc") == "Escape"
    assert normalize_key_name("escape") == "Escape"
    assert normalize_key_name("backspace") == "BackSpace"
    assert normalize_key_name("tab") == "Tab"
    assert normalize_key_name("ctrl") == "ctrl"
    assert normalize_key_name("control") == "ctrl"
    assert normalize_key_name("f5") == "F5"
    assert normalize_key_name("space") == "space"


def test_keyboard_controller_init():
    """Verify initialization in simulation / dry-run mode."""
    ctrl = KeyboardController(dry_run=True)
    assert ctrl.dry_run is True


@pytest.mark.asyncio
async def test_keyboard_type_simulation():
    """Verify typing text calculation, cadence, and duration estimation."""
    ctrl = KeyboardController(dry_run=True)
    res = await ctrl.type_text("Hello World", wpm=75, natural_delay=True)

    assert res["status"] == "success"
    assert res["action"] == "keyboard_type"
    assert res["text"] == "Hello World"
    assert res["characters_count"] == 11
    assert res["wpm"] == 75
    assert res["natural_delay"] is True
    assert res["estimated_duration_ms"] > 0
    assert res["is_unicode"] is False
    assert res["dry_run"] is True


@pytest.mark.asyncio
async def test_keyboard_type_arabic_mapping():
    """Verify Arabic character 9 (U+0669) is strictly mapped to Arabic letter jim (ج)."""
    ctrl = KeyboardController(dry_run=True)
    # Text with Arabic number 9: "\u0669"
    input_text = "اختبار ٩ هنا"
    res = await ctrl.type_text(input_text, wpm=80, natural_delay=False)

    assert res["status"] == "success"
    assert "\u0669" not in res["text"]
    assert "ج" in res["text"]
    assert res["text"] == "اختبار ج هنا"
    assert res["is_unicode"] is True


@pytest.mark.asyncio
async def test_keyboard_type_unicode_support():
    """Verify Unicode & Arabic string typing metrics."""
    ctrl = KeyboardController(dry_run=True)
    arabic_text = "مرحبا بكم في نظام mind"
    res = await ctrl.type_text(arabic_text, wpm=60, natural_delay=True)

    assert res["status"] == "success"
    assert res["text"] == arabic_text
    assert res["characters_count"] == len(arabic_text)
    assert res["is_unicode"] is True


@pytest.mark.asyncio
async def test_keyboard_type_empty():
    """Verify typing empty string returns immediately with 0 characters."""
    ctrl = KeyboardController(dry_run=True)
    res = await ctrl.type_text("", wpm=75)

    assert res["status"] == "success"
    assert res["characters_count"] == 0
    assert res["estimated_duration_ms"] == 0.0


@pytest.mark.asyncio
async def test_keyboard_press_keys():
    """Verify key pressing with various common key names."""
    ctrl = KeyboardController(dry_run=True)

    test_keys = [
        ("enter", "Return"),
        ("tab", "Tab"),
        ("escape", "Escape"),
        ("backspace", "BackSpace"),
        ("space", "space"),
        ("up", "Up"),
        ("down", "Down"),
        ("f11", "F11"),
    ]

    for key_in, key_norm in test_keys:
        res = await ctrl.press_key(key_in)
        assert res["status"] == "success"
        assert res["action"] == "keyboard_press"
        assert res["key"] == key_in
        assert res["normalized_key"] == key_norm
        assert res["dry_run"] is True


@pytest.mark.asyncio
async def test_keyboard_press_empty():
    """Verify pressing empty key returns error status."""
    ctrl = KeyboardController(dry_run=True)
    res = await ctrl.press_key("   ")
    assert res["status"] == "error"
    assert "cannot be empty" in res["message"]


@pytest.mark.asyncio
async def test_keyboard_hotkeys():
    """Verify hotkey combination normalization and dispatch."""
    ctrl = KeyboardController(dry_run=True)

    test_combos = [
        (["ctrl", "c"], "ctrl+c"),
        (["ctrl", "v"], "ctrl+v"),
        (["alt", "tab"], "alt+Tab"),
        (["ctrl", "shift", "t"], "ctrl+shift+t"),
        (["super", "d"], "super+d"),
    ]

    for keys_in, expected_combo in test_combos:
        res = await ctrl.hotkey(keys_in)
        assert res["status"] == "success"
        assert res["action"] == "keyboard_hotkey"
        assert res["keys"] == keys_in
        assert res["combo"] == expected_combo
        assert res["dry_run"] is True


@pytest.mark.asyncio
async def test_keyboard_hotkey_empty():
    """Verify hotkey with empty list returns error status."""
    ctrl = KeyboardController(dry_run=True)
    res = await ctrl.hotkey([])
    assert res["status"] == "error"


def test_mcp_server_keyboard_tools_registered():
    """Verify keyboard tools are registered on FastMCP server instance."""
    server = create_mcp_server()
    registered = [tool.name for tool in server._tool_manager.list_tools()]

    assert "keyboard_type" in registered
    assert "keyboard_press" in registered
    assert "keyboard_hotkey" in registered


@pytest.mark.asyncio
async def test_mcp_server_keyboard_tool_execution():
    """Verify invoking keyboard tools through the FastMCP server manager."""
    server = create_mcp_server()
    tool_map = {tool.name: tool for tool in server._tool_manager.list_tools()}

    # 1. keyboard_type
    type_res = await tool_map["keyboard_type"].fn(text="Hello Antigravity ٩", wpm=70, natural_delay=False)
    assert type_res["status"] == "success"
    assert type_res["text"] == "Hello Antigravity ج"

    # 2. keyboard_press
    press_res = await tool_map["keyboard_press"].fn(key="return")
    assert press_res["status"] == "success"
    assert press_res["normalized_key"] == "Return"

    # 3. keyboard_hotkey
    hotkey_res = await tool_map["keyboard_hotkey"].fn(keys=["ctrl", "a"])
    assert hotkey_res["status"] == "success"
    assert hotkey_res["combo"] == "ctrl+a"
