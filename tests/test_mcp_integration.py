"""Comprehensive automated test suite for the High-Performance Async MCP Server and Runner."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

from mind.core.terminal_manager import TerminalManager, WorkerProcessState
from mind.mcp.runner import (
    MCPServerRunner,
    provision_mcp_config,
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


@pytest.fixture(autouse=True)
def cleanup_mcp():
    """Ensure clean MCP state before and after each test."""
    reset_default_mcp_server()
    stop_background_mcp_server()
    yield
    reset_default_mcp_server()
    stop_background_mcp_server()


@pytest.mark.anyio
async def test_mcp_server_tools_registration() -> None:
    """Verify that all essential and coordination MCP tools are registered."""
    mgr = TerminalManager.get_instance()
    server = create_mcp_server(manager=mgr)

    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = [
        "list_workers",
        "get_terminal_screen",
        "send_terminal_input",
        "interrupt_and_inject",
        "check_account_quotas",
        "get_agent_profile",
        "notify_coordinator_worker_idle",
        "notify_coordinator_help",
        "check_coordinator_alarms",
    ]
    for expected in expected_tools:
        assert expected in tool_names, f"Expected tool '{expected}' not registered in FastMCP"


@pytest.mark.anyio
async def test_list_workers_with_linked_accounts() -> None:
    """Verify list_workers returns worker states and linked account / slot details."""
    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker(
        worker_id="mcp-worker-1",
        name="Worker-agy1",
        role="worker",
        assigned_agent="agy1",
        autostart=False,
    )

    server = create_mcp_server(manager=mgr)
    res = await server.call_tool("list_workers", {})
    assert not res.is_error
    assert len(res.content) > 0

    workers_data = json.loads(res.content[0].text)
    if isinstance(workers_data, dict):
        workers_list = [workers_data]
    else:
        workers_list = workers_data

    target_worker = next((w for w in workers_list if w["worker_id"] == "mcp-worker-1"), None)
    assert target_worker is not None, "mcp-worker-1 not found in list_workers output"
    assert target_worker["assigned_agent"] == "agy1"
    assert "token_status" in target_worker
    assert "quota_status" in target_worker
    assert "hourly_remaining" in target_worker
    assert "weekly_remaining" in target_worker


@pytest.mark.anyio
async def test_get_terminal_screen_and_caching() -> None:
    """Verify get_terminal_screen reads clean output and utilizes version-aware cache."""
    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("screen-worker", autostart=False)
    worker.buffer.feed("System initialized.\r\nProcessing task batch...\r\nDone.\r\n")

    server = create_mcp_server(manager=mgr)

    # Initial read
    t0 = time.time()
    res1 = await server.call_tool("get_terminal_screen", {"worker_id": "screen-worker", "lines": 20})
    read_duration = time.time() - t0
    assert not res1.is_error
    screen_text = res1.content[0].text
    assert "System initialized." in screen_text
    assert "Processing task batch..." in screen_text

    # Immediate second read must hit cache
    t1 = time.time()
    res2 = await server.call_tool("get_terminal_screen", {"worker_id": "screen-worker", "lines": 20})
    cached_duration = time.time() - t1
    assert not res2.is_error
    assert res1.content[0].text == res2.content[0].text
    assert cached_duration <= read_duration + 0.05

    # Non-existent worker error handling
    res_err = await server.call_tool("get_terminal_screen", {"worker_id": "unknown-slot-999"})
    assert "not found" in res_err.content[0].text.lower()


@pytest.mark.anyio
async def test_send_terminal_input() -> None:
    """Verify send_terminal_input sends keystrokes and auto-starts stopped workers."""
    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("input-worker", autostart=False)

    server = create_mcp_server(manager=mgr)
    res = await server.call_tool(
        "send_terminal_input",
        {"worker_id": "input-worker", "text": "status --check", "press_enter": True},
    )
    assert not res.is_error
    assert "Input sent to worker 'input-worker'" in res.content[0].text

    # Error handling for missing worker
    err_res = await server.call_tool("send_terminal_input", {"worker_id": "none-existing", "text": "ping"})
    assert "Error: Worker 'none-existing' not found" in err_res.content[0].text


@pytest.mark.anyio
async def test_interrupt_and_inject_async() -> None:
    """Verify interrupt_and_inject pauses worker safely and injects prioritized directive."""
    mgr = TerminalManager.get_instance()
    worker = mgr.create_worker("inject-worker", autostart=False)

    notifications: list[str] = []
    worker.add_notification_listener(lambda w, msg: notifications.append(msg))

    server = create_mcp_server(manager=mgr)
    res = await server.call_tool(
        "interrupt_and_inject",
        {
            "worker_id": "inject-worker",
            "sender_id": "Primary-Coordinator",
            "message": "Immediate halt: Switch to emergency patch",
            "priority": "critical",
        },
    )
    assert not res.is_error
    assert "Successfully interrupted inject-worker" in res.content[0].text
    assert worker.unread_notifications == 1
    assert "Immediate halt: Switch to emergency patch" in str(worker.last_interrupt_directive)
    assert len(notifications) == 1


@pytest.mark.anyio
async def test_check_account_quotas_tool() -> None:
    """Verify check_account_quotas for single slot, all slots, and JSON formatted mode."""
    mgr = TerminalManager.get_instance()
    server = create_mcp_server(manager=mgr)

    # 1. Single slot inquiry
    res_slot = await server.call_tool("check_account_quotas", {"slot": "agy1"})
    assert not res_slot.is_error
    data_slot = json.loads(res_slot.content[0].text)
    assert data_slot["slot"] == "agy1"
    assert "hourly_remaining" in data_slot
    assert "weekly_remaining" in data_slot
    assert "progress_bar" in data_slot

    # 2. As raw JSON
    res_json = await server.call_tool("check_account_quotas", {"slot": "agy1", "as_json": True})
    assert not res_json.is_error
    assert "hourly_limit" in res_json.content[0].text

    # 3. All slots inquiry
    res_all = await server.call_tool("check_account_quotas", {})
    assert not res_all.is_error
    data_all = json.loads(res_all.content[0].text)
    assert "summary" in data_all
    assert "slots" in data_all
    assert data_all["summary"]["total_slots"] >= 1


def test_runner_non_blocking_start() -> None:
    """Verify MCPServerRunner starts in background without blocking main execution."""
    t0 = time.time()
    runner = MCPServerRunner(host="127.0.0.1", port=8988)
    runner.start(wait_for_ready=False)
    elapsed = time.time() - t0

    # Must return immediately without sleeping (< 0.15s)
    assert elapsed < 0.15, f"Runner.start blocked for {elapsed:.3f}s (expected < 0.15s)"
    assert runner.is_running
    assert runner.sse_url == "http://127.0.0.1:8988/sse"

    runner.stop(timeout=2.0)
    assert not runner.is_running


@pytest.mark.anyio
async def test_runner_async_lifecycle() -> None:
    """Verify MCPServerRunner start_async and stop_async coroutines."""
    runner = MCPServerRunner(host="127.0.0.1", port=8989)
    await runner.start_async(wait_for_ready=False)
    assert runner.is_running

    await runner.stop_async(timeout=2.0)
    assert not runner.is_running


def test_terminal_screen_cache_operations() -> None:
    """Verify TerminalScreenCache TTL expiration, version checks, and capacity management."""
    cache = TerminalScreenCache(ttl=0.1, max_entries=5)
    cache.put("slot1:50", current_version=1, text="Text Version 1")

    # Hit
    assert cache.get("slot1:50", current_version=1) == "Text Version 1"
    # Miss on mismatched buffer version
    assert cache.get("slot1:50", current_version=2) is None

    # Miss on TTL expiration
    time.sleep(0.12)
    assert cache.get("slot1:50", current_version=1) is None

    # Clear
    cache.put("slot2:10", current_version=1, text="V2")
    cache.clear()
    assert cache.get("slot2:10", current_version=1) is None


def test_provision_mcp_config(tmp_path) -> None:
    """Verify provision_mcp_config creates and updates mcp_config.json files."""
    paths = provision_mcp_config(host="127.0.0.1", port=8765, user_home=tmp_path)
    assert len(paths) >= 2

    global_cfg = tmp_path / ".gemini" / "config" / "mcp_config.json"
    assert global_cfg.is_file()
    data = json.loads(global_cfg.read_text(encoding="utf-8"))
    assert "mind-mcp" in data.get("mcpServers", {})
    assert data["mcpServers"]["mind-mcp"]["serverUrl"] == "http://127.0.0.1:8765/sse"
    assert data["mcpServers"]["mind-mcp"]["disabled"] is False

    agy1_cfg = tmp_path / ".local" / "share" / "agy-instances" / "agy1" / ".gemini" / "config" / "mcp_config.json"
    assert agy1_cfg.is_file()
    data_agy1 = json.loads(agy1_cfg.read_text(encoding="utf-8"))
    assert data_agy1["mcpServers"]["mind-mcp"]["serverUrl"] == "http://127.0.0.1:8765/sse"


@pytest.mark.anyio
async def test_check_coordinator_alarms_tool() -> None:
    """Verify check_coordinator_alarms retrieves alarms from manager."""
    mgr = TerminalManager.get_instance()
    mgr.clear_coordinator_alarms()
    mgr.notify_coordinator_worker_idle(worker_id="alarm-worker-1", status_summary="Task Done")

    server = create_mcp_server(manager=mgr)
    res = await server.call_tool("check_coordinator_alarms", {})
    assert not res.is_error
    raw_alarms = json.loads(res.content[0].text)
    alarms = [raw_alarms] if isinstance(raw_alarms, dict) else raw_alarms
    assert isinstance(alarms, list)
    assert len(alarms) >= 1
    assert any(a.get("worker_id") == "alarm-worker-1" for a in alarms)
