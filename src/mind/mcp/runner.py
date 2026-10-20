"""Background and stdio execution runners for the embedded mind-mcp server."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import uvicorn

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]

from mind.mcp.server import get_default_mcp_server

logger = logging.getLogger("mind.mcp.runner")


class MCPServerRunner:
    """Manages background lifecycle of the embedded MCP SSE server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        server: FastMCP | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.server = server or get_default_mcp_server()
        self._uvicorn_server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False

    @property
    def sse_url(self) -> str:
        """The HTTP SSE endpoint URL for MCP clients (such as agy)."""
        return f"http://{self.host}:{self.port}/sse"

    @property
    def is_running(self) -> bool:
        return self._is_running and (self._thread.is_alive() if self._thread else False)

    def start(self, wait_for_ready: bool = True, timeout: float = 3.0) -> None:
        """Start the MCP SSE server in a background daemon thread."""
        if self.is_running:
            return

        app = self.server.sse_app()
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="error",
            access_log=False,
        )
        self._uvicorn_server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._uvicorn_server.run,
            name="mind-mcp-server",
            daemon=True,
        )
        self._thread.start()
        self._is_running = True

        if wait_for_ready:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._uvicorn_server.started:
                    break
                time.sleep(0.05)

    def stop(self, timeout: float = 2.0) -> None:
        """Gracefully signal the server to stop and wait for completion."""
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._is_running = False
        self._uvicorn_server = None
        self._thread = None


_global_runner: MCPServerRunner | None = None
_runner_lock = threading.Lock()


def start_background_mcp_server(
    host: str = "127.0.0.1",
    port: int = 8765,
) -> MCPServerRunner:
    """Start or retrieve the global background MCP server runner."""
    global _global_runner
    with _runner_lock:
        if _global_runner is None or not _global_runner.is_running:
            _global_runner = MCPServerRunner(host=host, port=port)
            _global_runner.start()
        return _global_runner


def stop_background_mcp_server() -> None:
    """Stop the global background MCP server runner if active."""
    global _global_runner
    with _runner_lock:
        if _global_runner is not None:
            _global_runner.stop()
            _global_runner = None


def run_stdio_mcp_server() -> None:
    """Run the MCP server in foreground stdio mode (for stdio-based MCP clients)."""
    server = get_default_mcp_server()
    server.run(transport="stdio")
