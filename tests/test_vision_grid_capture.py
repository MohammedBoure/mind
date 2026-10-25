"""Comprehensive test suite for Screen Vision Capture and Numbered Coordinate Grid MCP tools."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from PIL import Image
import pytest

from mind.mcp.server import create_mcp_server, reset_default_mcp_server
from mind.mcp.vision_capture import (
    capture_raw_screen,
    capture_screen_with_grid,
    draw_coordinate_grid,
    encode_vision_capture,
    generate_mock_screen,
    get_font,
    get_screen_geometry,
    is_display_available,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Ensure clean global MCP server state."""
    reset_default_mcp_server()
    yield
    reset_default_mcp_server()


def test_get_font_cached_and_fallback() -> None:
    """Verify font loader returns valid font and caches by size."""
    f1 = get_font(12)
    f2 = get_font(12)
    assert f1 is f2  # Cached instance
    f3 = get_font(18)
    assert f3 is not None


def test_get_screen_geometry() -> None:
    """Verify screen geometry inspection returns valid dimensions and monitor list."""
    geom = get_screen_geometry()
    assert isinstance(geom, dict)
    assert "width" in geom and geom["width"] > 0
    assert "height" in geom and geom["height"] > 0
    assert "monitors" in geom and len(geom["monitors"]) > 0
    assert "is_headless" in geom
    assert "primary_monitor" in geom
    assert "scale_factor" in geom

    first_mon = geom["monitors"][0]
    assert "index" in first_mon
    assert "width" in first_mon and first_mon["width"] > 0
    assert "height" in first_mon and first_mon["height"] > 0


def test_generate_mock_screen() -> None:
    """Verify headless mock screen generator creates simulated desktop canvas."""
    img = generate_mock_screen(width=1280, height=720)
    assert isinstance(img, Image.Image)
    assert img.size == (1280, 720)
    assert img.mode == "RGB"


def test_draw_coordinate_grid_calibration() -> None:
    """Verify numbered coordinate grid overlay correctly composites onto image."""
    base_img = Image.new("RGB", (1000, 600), color=(30, 30, 30))
    gridded_img, calib = draw_coordinate_grid(
        image=base_img,
        grid_step=100,
        show_axes=True,
        show_labels=True,
        show_intersections=True,
        show_badges=True,
    )
    assert gridded_img.size == (1000, 600)
    assert gridded_img.mode == "RGB"
    assert calib["origin_x"] == 0
    assert calib["origin_y"] == 0
    assert calib["step_x"] == 100
    assert calib["step_y"] == 100
    assert calib["width"] == 1000
    assert calib["height"] == 600


def test_draw_coordinate_grid_options() -> None:
    """Verify grid options such as disabled axes and badges."""
    base_img = Image.new("RGB", (800, 600), color=(20, 20, 20))
    gridded_img, calib = draw_coordinate_grid(
        image=base_img,
        grid_step=50,
        show_axes=False,
        show_labels=False,
        show_intersections=False,
        show_badges=False,
    )
    assert gridded_img.size == (800, 600)
    assert calib["step_x"] == 50


def test_encode_vision_capture_base64() -> None:
    """Verify base64 encoding returns valid image data URL and byte size."""
    test_img = Image.new("RGB", (300, 200), color=(50, 50, 50))
    calib = {"step_x": 100, "width": 300, "height": 200}
    res = encode_vision_capture(
        image=test_img,
        calibration=calib,
        output_format="base64",
        image_format="jpeg",
        quality=80,
    )
    assert res["success"] is True
    assert res["format"] == "jpeg"
    assert res["mime_type"] == "image/jpeg"
    assert "data_url" in res
    assert res["data_url"].startswith("data:image/jpeg;base64,")
    assert "base64" in res
    raw_bytes = base64.b64decode(res["base64"])
    assert len(raw_bytes) > 0


def test_encode_vision_capture_file_output() -> None:
    """Verify file output saves gridded image to disk and returns path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dest_file = Path(tmpdir) / "output_test.png"
        test_img = Image.new("RGB", (400, 300), color=(40, 40, 40))
        calib = {"step_x": 50, "width": 400, "height": 300}
        res = encode_vision_capture(
            image=test_img,
            calibration=calib,
            output_format="file",
            image_format="png",
            output_path=str(dest_file),
        )
        assert res["success"] is True
        assert res["file_path"] == str(dest_file)
        assert dest_file.exists()
        assert res["file_size_bytes"] > 0


def test_headless_fallback_resilience() -> None:
    """Verify capture cleanly falls back to mock screen when display is unavailable."""
    with patch("mss.MSS", side_effect=Exception("Display unreachable")), \
         patch("PIL.ImageGrab.grab", side_effect=Exception("No X server")):
        geom = get_screen_geometry()
        assert geom["is_headless"] is True

        res = capture_screen_with_grid(grid_step=100, output_format="base64")
        assert res["success"] is True
        assert res["is_headless"] is True
        assert res["width"] > 0
        assert res["height"] > 0
        assert "data_url" in res


@pytest.mark.anyio
async def test_mcp_server_capture_screen_with_grid_tool() -> None:
    """Verify capture_screen_with_grid is exposed as an MCP tool and callable."""
    server = create_mcp_server()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "capture_screen_with_grid" in tool_names
    assert "get_screen_geometry" in tool_names

    # Call capture_screen_with_grid tool
    tool_res = await server.call_tool(
        "capture_screen_with_grid",
        {"grid_step": 100, "show_axes": True, "output_format": "base64", "quality": 85},
    )
    assert not tool_res.is_error
    assert len(tool_res.content) > 0

    payload = json.loads(tool_res.content[0].text)
    assert payload.get("success") is True
    assert "width" in payload
    assert "height" in payload
    assert payload.get("grid_step") == 100
    assert "data_url" in payload
    assert "calibration" in payload


@pytest.mark.anyio
async def test_mcp_server_get_screen_geometry_tool() -> None:
    """Verify get_screen_geometry tool is exposed and callable via FastMCP."""
    server = create_mcp_server()
    tool_res = await server.call_tool("get_screen_geometry", {})
    assert not tool_res.is_error
    assert len(tool_res.content) > 0

    payload = json.loads(tool_res.content[0].text)
    assert "width" in payload
    assert "height" in payload
    assert "monitors" in payload
    assert "is_headless" in payload
