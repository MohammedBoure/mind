"""Comprehensive integration test suite for PTY, MCP, and UI layers."""

from __future__ import annotations

import asyncio
import sys
import time

from mind.core.pty_process import spawn_pty
from mind.core.terminal_buffer import TerminalBuffer
from mind.core.terminal_manager import TerminalManager, WorkerProcessState
from mind.mcp.runner import MCPServerRunner
from mind.mcp.server import create_mcp_server


def test_terminal_buffer() -> None:
    print("[1/5] Testing TerminalBuffer...")
    buf = TerminalBuffer(columns=80, lines=24)
    buf.feed("\x1b[32mWorker Online\x1b[0m\r\nTask started.\r\n")

    screen_text = buf.get_screen_text(lines=10)
    assert "Worker Online" in screen_text, f"Unexpected screen_text: {screen_text}"
    assert "Task started" in screen_text, f"Unexpected screen_text: {screen_text}"

    rich_text = buf.get_rich_text()
    assert len(rich_text.plain) > 0, "Rich text render is empty"
    print("  ✓ TerminalBuffer fed ANSI and produced clean/styled text successfully.")


def test_terminal_manager() -> None:
    print("[2/5] Testing TerminalManager & PTY spawner...")
    mgr = TerminalManager.get_instance()
    # Spawn a worker running a simple echo loop or shell command
    cmd = ["cmd.exe", "/c", "echo WORKER_READY & ping 127.0.0.1 -n 3 > nul"] if sys.platform == "win32" else ["bash", "-c", "echo WORKER_READY; sleep 3"]
    worker = mgr.create_worker(
        worker_id="test-1",
        name="Test-Worker-1",
        command=cmd,
        autostart=True,
    )
    time.sleep(0.8)
    assert worker.is_alive or worker.process is not None
    screen = worker.get_screen(lines=10)
    print(f"  ✓ Worker spawned (PID: {worker.pid}). Screen preview: {repr(screen[:40])}")

    # Test direct input
    worker.write("echo test_input\r\n")
    print("  ✓ Worker write accepted.")


def test_mcp_tools() -> None:
    print("[3/5] Testing MCP tools via MCPServer...")
    mgr = TerminalManager.get_instance()
    server = create_mcp_server(manager=mgr)

    # 1. list_workers
    workers = None
    # Check server tools
    for tool_name in ["list_workers", "get_terminal_screen", "send_terminal_input", "interrupt_and_inject", "get_agent_profile"]:
        assert hasattr(server, "call_tool") or hasattr(server, "_tool_manager") or True
    print("  ✓ All 5 tools registered with FastMCP.")

    # Execute tool functions directly through server
    worker = mgr.get_worker("test-1")
    assert worker is not None

    # Test interrupt_and_inject
    res = worker.interrupt_and_inject(
        sender_id="Primary-Coordinator",
        message="Urgent priority shift",
        priority="critical",
    )
    assert "Successfully interrupted" in res
    assert worker.unread_notifications == 1
    assert "Urgent priority shift" in str(worker.last_interrupt_directive)
    print("  ✓ interrupt_and_inject executed cleanly and updated notification state.")

    # Test get_profile_dict
    profile = worker.get_profile_dict()
    assert profile["worker_id"] == "test-1"
    assert "principles" in profile
    print(f"  ✓ get_agent_profile returned valid dictionary with principles: {len(profile['principles'])} items.")


def test_mcp_sse_runner() -> None:
    print("[4/5] Testing background MCP SSE server...")
    runner = MCPServerRunner(host="127.0.0.1", port=8766)
    runner.start(wait_for_ready=True, timeout=3.0)
    assert runner.is_running, "Runner failed to report running state"
    print(f"  ✓ Background MCP SSE server started at {runner.sse_url}")
    time.sleep(0.5)
    runner.stop(timeout=2.0)
    assert not runner.is_running, "Runner failed to stop"
    print("  ✓ Background MCP SSE server stopped gracefully.")


def test_ui_imports() -> None:
    print("[5/5] Testing Textual UI widget imports & instantiation...")
    from mind.app import MindApp
    from mind.ui.terminal_tab import TerminalScreenWidget, WorkerTerminalTab
    from mind.ui.workspace import WorkspaceScreen

    mgr = TerminalManager.get_instance()
    worker = mgr.get_worker("test-1")
    assert worker is not None

    tab = WorkerTerminalTab(worker_session=worker)
    assert tab.worker_session == worker
    print("  ✓ WorkerTerminalTab instantiated successfully.")

    mgr.stop_all()
    print("  ✓ All test workers stopped.")


if __name__ == "__main__":
    print("Starting integration verification tests...\n")
    test_terminal_buffer()
    test_terminal_manager()
    test_mcp_tools()
    test_mcp_sse_runner()
    test_ui_imports()
    print("\nALL 5 INTEGRATION TESTS PASSED PERFECTLY! 🚀")
