"""Comprehensive test suite for Natural Human Mouse MCP tools and controller."""

from __future__ import annotations

import asyncio
from typing import Any
import pytest

from mind.mcp.natural_mouse import (
    NaturalMouseController,
    get_natural_mouse_controller,
    is_headless_environment,
    reset_natural_mouse_controller,
)
from mind.mcp.server import create_mcp_server, reset_default_mcp_server


@pytest.fixture(autouse=True)
def clean_state():
    """Ensure clean global controller and MCP server state before and after each test."""
    reset_default_mcp_server()
    reset_natural_mouse_controller()
    yield
    reset_default_mcp_server()
    reset_natural_mouse_controller()


def test_is_headless_environment():
    """Verify headless detection correctly reports boolean."""
    res = is_headless_environment()
    assert isinstance(res, bool)


def test_controller_initialization():
    """Verify NaturalMouseController initializes with sensible defaults and persistent state."""
    ctrl = NaturalMouseController(dry_run=True)
    assert ctrl.dry_run is True
    assert ctrl.screen_w > 0
    assert ctrl.screen_h > 0
    assert len(ctrl.virtual_pos) == 2

    pos = ctrl.get_position()
    assert pos["status"] == "success"
    assert "x" in pos and "y" in pos
    assert pos["dry_run"] is True
    assert pos["mode"] == "headless_simulation"


@pytest.mark.asyncio
async def test_natural_mouse_move():
    """Verify natural_mouse_move computes realistic trajectories and updates coordinates."""
    ctrl = NaturalMouseController(dry_run=True)
    initial_pos = ctrl.get_position()

    result = await ctrl.move(target_x=800.0, target_y=600.0)
    assert result["status"] == "success"
    assert result["action"] == "natural_mouse_move"
    assert result["from"]["x"] == initial_pos["x"]
    assert result["from"]["y"] == initial_pos["y"]
    assert result["to"]["x"] == 800.0
    assert result["to"]["y"] == 600.0
    assert result["steps"] > 10
    assert result["duration_ms"] > 0
    assert result["dry_run"] is True

    # Coordinates must persist
    new_pos = ctrl.get_position()
    assert new_pos["x"] == 800.0
    assert new_pos["y"] == 600.0


@pytest.mark.asyncio
async def test_natural_mouse_move_custom_duration():
    """Verify move with explicitly specified duration_ms."""
    ctrl = NaturalMouseController(dry_run=True)
    result = await ctrl.move(target_x=450.0, target_y=350.0, duration_ms=500.0)
    assert result["status"] == "success"
    assert result["duration_ms"] == 500.0
    assert result["to"]["x"] == 450.0
    assert result["to"]["y"] == 350.0


@pytest.mark.asyncio
async def test_natural_mouse_click():
    """Verify natural_mouse_click executes movement to target and registers click parameters."""
    ctrl = NaturalMouseController(dry_run=True)
    result = await ctrl.click(target_x=720.0, target_y=480.0, button="right", clicks=2)

    assert result["status"] == "success"
    assert result["action"] == "natural_mouse_click"
    assert result["clicked_at"]["x"] == 720.0
    assert result["clicked_at"]["y"] == 480.0
    assert result["button"] == "right"
    assert result["clicks"] == 2
    assert result["move_steps"] > 5
    assert result["dry_run"] is True

    pos = ctrl.get_position()
    assert pos["x"] == 720.0
    assert pos["y"] == 480.0


@pytest.mark.asyncio
async def test_natural_mouse_sequence_tuple_list():
    """Verify sequence of coordinates formatted as list of (x, y) tuples."""
    ctrl = NaturalMouseController(dry_run=True)
    targets = [(200.0, 150.0), (500.0, 300.0), (800.0, 600.0)]

    result = await ctrl.sequence(coordinates=targets, delay_between=0.05, click_targets=True)
    assert result["status"] == "success"
    assert result["action"] == "natural_mouse_sequence"
    assert result["targets_count"] == 3
    assert result["final_position"]["x"] == 800.0
    assert result["final_position"]["y"] == 600.0
    assert result["click_targets"] is True
    assert result["total_steps"] > 30

    pos = ctrl.get_position()
    assert pos["x"] == 800.0
    assert pos["y"] == 600.0


@pytest.mark.asyncio
async def test_natural_mouse_sequence_dicts_and_strings():
    """Verify sequence parsing handles dicts and string coordinates."""
    ctrl = NaturalMouseController(dry_run=True)
    targets = [
        {"x": 100, "y": 200},
        "300, 400",
        [500, 600],
    ]

    result = await ctrl.sequence(coordinates=targets, delay_between=0.01)
    assert result["status"] == "success"
    assert result["targets_count"] == 3
    assert result["final_position"]["x"] == 500.0
    assert result["final_position"]["y"] == 600.0


@pytest.mark.asyncio
async def test_natural_mouse_sequence_empty():
    """Verify sequence handles empty or invalid inputs gracefully."""
    ctrl = NaturalMouseController(dry_run=True)
    result = await ctrl.sequence(coordinates=[])
    assert result["status"] == "error"
    assert "No valid coordinates" in result["message"]


def test_mcp_server_registration():
    """Verify all natural mouse tools are registered on the FastMCP server instance."""
    server = create_mcp_server()
    registered_tools = [tool.name for tool in server._tool_manager.list_tools()]

    expected_tools = [
        "natural_mouse_move",
        "natural_mouse_click",
        "natural_mouse_sequence",
        "get_mouse_position",
    ]
    for tool_name in expected_tools:
        assert tool_name in registered_tools, f"Missing expected tool: {tool_name}"


@pytest.mark.asyncio
async def test_mcp_server_tool_execution():
    """Verify invoking the MCP tools via the FastMCP server wrapper."""
    server = create_mcp_server()
    tool_map = {tool.name: tool for tool in server._tool_manager.list_tools()}

    # 1. get_mouse_position
    pos_res = await tool_map["get_mouse_position"].fn()
    assert pos_res["status"] == "success"
    assert "x" in pos_res and "y" in pos_res

    # 2. natural_mouse_move
    move_res = await tool_map["natural_mouse_move"].fn(target_x=650.0, target_y=350.0)
    assert move_res["status"] == "success"
    assert move_res["to"]["x"] == 650.0
    assert move_res["to"]["y"] == 350.0

    # 3. natural_mouse_click
    click_res = await tool_map["natural_mouse_click"].fn(target_x=700.0, target_y=400.0, button="left", clicks=1)
    assert click_res["status"] == "success"
    assert click_res["clicked_at"]["x"] == 700.0

    # 4. natural_mouse_sequence
    seq_res = await tool_map["natural_mouse_sequence"].fn(
        coordinates=[[100, 200], [400, 500]],
        delay_between=0.01,
        click_targets=False,
    )
    assert seq_res["status"] == "success"
    assert seq_res["final_position"]["x"] == 400.0
    assert seq_res["final_position"]["y"] == 500.0
