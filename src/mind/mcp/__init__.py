"""Model Context Protocol (MCP) server layer for the mind orchestrator."""

try:
    from mind.mcp.natural_mouse import (
        NaturalMouseController,
        get_natural_mouse_controller,
        is_headless_environment,
        reset_natural_mouse_controller,
    )
except ImportError:
    NaturalMouseController = None  # type: ignore[assignment, misc]
    get_natural_mouse_controller = None  # type: ignore[assignment]
    is_headless_environment = None  # type: ignore[assignment]
    reset_natural_mouse_controller = None  # type: ignore[assignment]
from mind.mcp.runner import (
    MCPServerRunner,
    run_stdio_mcp_server,
    run_stdio_mcp_server_async,
    start_background_mcp_server,
    stop_background_mcp_server,
)
from mind.mcp.server import (
    TerminalScreenCache,
    create_mcp_server,
    get_default_mcp_server,
    reset_default_mcp_server,
)
from mind.mcp.vision_capture import (
    GridCalibration,
    MonitorGeometry,
    ScreenGeometry,
    capture_raw_screen,
    capture_screen_with_grid,
    draw_coordinate_grid,
    encode_vision_capture,
    generate_mock_screen,
    get_screen_geometry,
    is_display_available,
)

__all__ = [
    "GridCalibration",
    "MCPServerRunner",
    "MonitorGeometry",
    "NaturalMouseController",
    "ScreenGeometry",
    "TerminalScreenCache",
    "capture_raw_screen",
    "capture_screen_with_grid",
    "create_mcp_server",
    "draw_coordinate_grid",
    "encode_vision_capture",
    "generate_mock_screen",
    "get_default_mcp_server",
    "get_mouse_position",
    "get_natural_mouse_controller",
    "get_screen_geometry",
    "is_display_available",
    "is_headless_environment",
    "reset_default_mcp_server",
    "reset_natural_mouse_controller",
    "run_stdio_mcp_server",
    "run_stdio_mcp_server_async",
    "start_background_mcp_server",
    "stop_background_mcp_server",
]
