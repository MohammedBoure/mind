"""Background and stdio execution runners for the embedded mind-mcp server.

Supports dual transports:
1. Local HTTP SSE server (default on 127.0.0.1:8765) running asynchronously
   without blocking the main application thread (`wait_for_ready=False`).
2. Standard I/O (stdio) transport for direct Antigravity CLI integration.
"""

from __future__ import annotations

import asyncio
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
    """Manages background lifecycle of the embedded MCP SSE server.

    Designed to be fully asyncio-native and non-blocking (`wait_for_ready=False`),
    preventing any delays in main application startup and UI event loops.
    """

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
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._is_running = False
        self._lock = threading.Lock()

    @property
    def sse_url(self) -> str:
        """The HTTP SSE endpoint URL for MCP clients (such as agy)."""
        return f"http://{self.host}:{self.port}/sse"

    @property
    def is_running(self) -> bool:
        """Indicate whether the server process or background task is actively running."""
        thread_alive = bool(self._thread and self._thread.is_alive())
        task_alive = bool(self._task and not self._task.done())
        server_started = bool(self._uvicorn_server and self._uvicorn_server.started)
        return self._is_running and (thread_alive or task_alive or server_started)

    def start(self, wait_for_ready: bool = False, timeout: float = 3.0) -> None:
        """Start the MCP SSE server in a background daemon thread without blocking.

        Args:
            wait_for_ready: Whether to block until server is listening (default: False).
            timeout: Maximum seconds to wait if wait_for_ready is True (default: 3.0).
        """
        with self._lock:
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

            def _run_server_thread() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                try:
                    loop.run_until_complete(self._uvicorn_server.serve())
                except asyncio.CancelledError:
                    pass
                except (Exception, SystemExit, BaseException) as exc:
                    logger.debug("MCP background server thread encountered error: %s", exc)
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass

            self._thread = threading.Thread(
                target=_run_server_thread,
                name="mind-mcp-server",
                daemon=True,
            )
            self._thread.start()
            self._is_running = True

        if wait_for_ready:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._uvicorn_server and self._uvicorn_server.started:
                    break
                time.sleep(0.02)

    def stop(self, timeout: float = 2.0) -> None:
        """Gracefully signal the server to stop and release all background resources."""
        with self._lock:
            if self._uvicorn_server:
                self._uvicorn_server.should_exit = True
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
            if self._task and not self._task.done():
                self._task.cancel()
            self._is_running = False
            self._uvicorn_server = None
            self._thread = None
            self._task = None
            self._loop = None

    async def serve_async(self) -> None:
        """Serve the MCP SSE server directly as a native coroutine in the active event loop."""
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
        self._is_running = True
        try:
            await self._uvicorn_server.serve()
        finally:
            self._is_running = False

    async def start_async(self, wait_for_ready: bool = False, timeout: float = 3.0) -> asyncio.Task:
        """Start the server as a background asyncio task in the active event loop."""
        with self._lock:
            if self.is_running and self._task:
                return self._task

            app = self.server.sse_app()
            config = uvicorn.Config(
                app=app,
                host=self.host,
                port=self.port,
                log_level="error",
                access_log=False,
            )
            self._uvicorn_server = uvicorn.Server(config)
            self._is_running = True
            self._task = asyncio.create_task(self._uvicorn_server.serve())

        if wait_for_ready:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._uvicorn_server.started:
                    break
                await asyncio.sleep(0.02)

        return self._task

    async def stop_async(self, timeout: float = 2.0) -> None:
        """Gracefully signal the server to stop within an async context."""
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self.stop(timeout=timeout)


_global_runner: MCPServerRunner | None = None
_runner_lock = threading.Lock()


def start_background_mcp_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    wait_for_ready: bool = False,
) -> MCPServerRunner:
    """Start or retrieve the global background MCP server runner.

    Defaults to non-blocking execution (`wait_for_ready=False`) to avoid pausing
    the main application lifecycle.
    """
    global _global_runner
    with _runner_lock:
        if _global_runner is None or not _global_runner.is_running:
            _global_runner = MCPServerRunner(host=host, port=port)
            _global_runner.start(wait_for_ready=wait_for_ready)
        return _global_runner


def stop_background_mcp_server() -> None:
    """Stop the global background MCP server runner if active."""
    global _global_runner
    with _runner_lock:
        if _global_runner is not None:
            _global_runner.stop()
            _global_runner = None


async def run_stdio_mcp_server_async(server: FastMCP | None = None) -> None:
    """Run the MCP server in foreground stdio mode natively with asyncio.

    Connects standard I/O streams directly for CLI clients such as Antigravity.
    """
    srv = server or get_default_mcp_server()
    await srv.run_stdio_async()


def run_stdio_mcp_server(server: FastMCP | None = None) -> None:
    """Run the MCP server in foreground stdio mode (blocking CLI entrypoint)."""
    srv = server or get_default_mcp_server()
    try:
        import anyio
        anyio.run(srv.run_stdio_async)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as exc:
        logger.error("Stdio MCP server exited with error: %s", exc)
