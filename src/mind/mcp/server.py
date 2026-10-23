"""Embedded High-Performance Async MCP Server for the mind multi-agent system.

Exposes lightweight asyncio-native orchestration tools for the primary coordinator agent:
- `list_workers`: Inspect active workers, process states, and linked account/slot details.
- `get_terminal_screen`: Read live rendered terminal outputs with version-tracked caching.
- `send_terminal_input`: Write raw input and commands directly to the worker prompt.
- `interrupt_and_inject`: Safely halt current action with SIGINT and inject priority directives.
- `check_account_quotas`: Inspect hourly and weekly quota consumption and remaining limits.
- `get_agent_profile`: Query agent role, principles, local configs, and instructions.
- `notify_coordinator_worker_idle`: Coordinator notification when worker finishes.
- `notify_coordinator_help`: Urgent assistance alarm for coordinator.
- `check_coordinator_alarms`: Retrieve unread coordinator alarms.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from typing import Any

import httpx

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]

from mind.core.terminal_manager import TerminalManager, WorkerSession
from mind.core.usage_monitor import UsageMonitor

logger = logging.getLogger("mind.mcp")


class TerminalScreenCache:
    """High-performance thread-safe cache for rendered terminal screen lines.

    Maintains version-aware and time-bounded entries to guarantee O(1) response
    times for repetitive screen polling without incurring buffer re-scanning.
    """

    def __init__(self, ttl: float = 0.25, max_entries: int = 128) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._cache: dict[str, tuple[int, float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, current_version: int) -> str | None:
        """Retrieve cached screen text if the buffer version and TTL remain valid."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            cached_version, cached_time, text = entry
            if cached_version == current_version and (time.time() - cached_time) < self.ttl:
                return text
            return None

    def put(self, key: str, current_version: int, text: str) -> None:
        """Store rendered screen text with current buffer version timestamp."""
        with self._lock:
            self._cache[key] = (current_version, time.time(), text)
            if len(self._cache) > self.max_entries:
                cutoff = time.time() - (self.ttl * 4)
                self._cache = {
                    k: v for k, v in self._cache.items() if v[1] > cutoff
                }

    def clear(self) -> None:
        """Flush all cached screen lines."""
        with self._lock:
            self._cache.clear()


# Module-level screen cache singleton
_screen_cache = TerminalScreenCache(ttl=0.25)


def _resolve_worker_account(worker: WorkerSession, usage_monitor: UsageMonitor) -> dict[str, Any]:
    """Extract linked account identity, token status, and quota summary for a worker slot."""
    slot_id = worker.get_slot_id() if hasattr(worker, "get_slot_id") else None
    assigned = getattr(worker, "assigned_agent", "") or ""
    slot_name = f"agy{slot_id}" if slot_id else (assigned or "agy1")

    account_info: dict[str, Any] = {
        "slot_id": slot_id,
        "assigned_agent": assigned,
        "linked_account": None,
        "token_status": "unknown",
        "quota_status": "unknown",
        "hourly_remaining": None,
        "weekly_remaining": None,
    }

    try:
        usage = usage_monitor.get_slot_usage(slot_name)
        account_info["linked_account"] = usage.email or usage.account
        account_info["token_status"] = usage.token_status
        account_info["quota_status"] = usage.status.value
        account_info["hourly_remaining"] = usage.hourly_remaining
        account_info["weekly_remaining"] = usage.weekly_remaining
    except Exception as exc:
        logger.debug("Failed resolving account for worker %s (%s): %s", worker.worker_id, slot_name, exc)

    return account_info


def create_mcp_server(manager: TerminalManager | None = None) -> FastMCP:
    """Create and configure the async-native mind-mcp server with all orchestration tools."""
    server = FastMCP(
        name="mind-mcp",
        instructions=(
            "Central High-Performance Async MCP bridge for the mind AI Multi-Agent Orchestrator. "
            "Allows the primary coordinator agent to inspect live worker terminal screens, "
            "inject inter-agent interrupt directives, send raw inputs to worker terminals, "
            "check account quota consumption, and query agent profiles."
        ),
    )

    mgr = manager or TerminalManager.get_instance()
    usage_monitor = UsageMonitor()
    is_custom_manager = (manager is not None)

    async def _forward_if_remote(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, Any]:
        """Forward tool call to running background mind MCP server if available.

        Returns:
            (True, result) if handled remotely by active server.
            (False, None) if should execute locally.
        """
        if is_custom_manager:
            return False, None
        if getattr(server, "_is_background_server", False):
            return False, None
        if os.environ.get("MIND_DISABLE_MCP_FORWARDING") == "1":
            return False, None

        port = int(os.environ.get("MIND_HTTP_PORT", "8765"))
        url = f"http://127.0.0.1:{port}/api/call-tool"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={"name": tool_name, "arguments": arguments})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        return True, data.get("result")
        except Exception:
            pass
        return False, None

    # ── Tool 1: list_workers ──────────────────────────────────────────
    @server.tool()
    async def list_workers() -> list[dict[str, Any]]:
        """List all active worker tabs, process states, and linked account/slot details.

        Returns:
            A list of dictionaries containing worker_id, agent_id, name, role,
            state ('running', 'paused', 'waiting_input', 'terminated'),
            process PID, model, task description, unread notifications,
            is_alive flag, linked slot_id, assigned_agent, linked_account email,
            token_status, quota_status, and remaining hourly/weekly quotas.
        """
        handled, remote_res = await _forward_if_remote("list_workers", {})
        if handled and isinstance(remote_res, list):
            return remote_res

        workers = mgr.list_workers()
        results: list[dict[str, Any]] = []

        for w in workers:
            acc_info = _resolve_worker_account(w, usage_monitor)
            results.append({
                "worker_id": w.worker_id,
                "agent_id": w.agent_id,
                "name": w.name,
                "role": getattr(w, "role", "worker"),
                "state": w.state.value if hasattr(w.state, "value") else str(w.state),
                "pid": w.pid,
                "model": w.model,
                "task": w.task,
                "unread_notifications": w.unread_notifications,
                "is_alive": w.is_alive,
                "slot_id": acc_info["slot_id"],
                "assigned_agent": acc_info["assigned_agent"],
                "linked_account": acc_info["linked_account"],
                "token_status": acc_info["token_status"],
                "quota_status": acc_info["quota_status"],
                "hourly_remaining": acc_info["hourly_remaining"],
                "weekly_remaining": acc_info["weekly_remaining"],
            })
        return results

    # ── Tool 2: get_terminal_screen ───────────────────────────────────
    @server.tool()
    async def get_terminal_screen(worker_id: str = "", lines: int = 50, target: str = "") -> str:
        """Read the rendered clean text content from a worker's terminal screen buffer.

        Inspects what the worker agent is currently viewing or outputting in its terminal,
        utilizing high-performance version-tracked caching.

        Args:
            worker_id: The identifier of the worker agent (e.g. '1', 'worker-1').
            lines: Number of recent lines to retrieve (default: 50, use 0 for entire buffer including scrollback history).
            target: Alias for worker_id.

        Returns:
            Rendered terminal text content, or an error message if not found.
        """
        actual_id = worker_id or target
        handled, remote_res = await _forward_if_remote(
            "get_terminal_screen",
            {"worker_id": actual_id, "lines": lines, "target": target},
        )
        if handled and isinstance(remote_res, str):
            return remote_res

        worker = mgr.get_worker(actual_id)
        if not worker:
            available = [w.worker_id for w in mgr.list_workers()]
            return f"Error: Worker '{actual_id}' not found. Available workers: {available}"

        req_lines = max(0, lines)
        cache_key = f"{actual_id}:{req_lines}"
        current_version = worker.buffer.version

        # 1. Fast cache lookup
        cached = _screen_cache.get(cache_key, current_version)
        if cached is not None:
            return cached

        # 2. Extract clean screen text from worker buffer
        screen_text = worker.get_screen(lines=req_lines)
        if not screen_text.strip():
            result = f"(Terminal buffer for Worker '{actual_id}' is currently empty or initializing)"
        else:
            result = screen_text

        # 3. Store in memory cache
        _screen_cache.put(cache_key, current_version, result)
        return result

    # ── Tool 2.5: restart_worker ──────────────────────────────────────
    @server.tool()
    async def restart_worker(worker_id: str = "", target: str = "") -> str:
        """Restart a stopped or dead worker session process.

        Args:
            worker_id: Identifier of the worker agent (e.g. '1', '2').
            target: Alias for worker_id.

        Returns:
            Status message.
        """
        actual_id = worker_id or target
        handled, remote_res = await _forward_if_remote(
            "restart_worker",
            {"worker_id": actual_id, "target": target},
        )
        if handled and isinstance(remote_res, str):
            return remote_res

        worker = mgr.get_worker(actual_id)
        if not worker:
            return f"Error: Worker '{actual_id}' not found."
        worker.restart()
        await asyncio.sleep(0.5)
        return f"Successfully restarted worker '{actual_id}'."

    # ── Tool 3: send_terminal_input ───────────────────────────────────
    @server.tool()
    async def send_terminal_input(
        worker_id: str = "",
        text: str = "",
        press_enter: bool = True,
        target: str = "",
    ) -> str:
        """Write raw input or commands directly to the worker terminal stdin.

        Args:
            worker_id: The identifier of the worker agent.
            text: Text, command, or keystrokes to deliver.
            press_enter: Whether to append a newline / enter key (default: True).
            target: Alias for worker_id.

        Returns:
            Status confirmation message.
        """
        actual_id = worker_id or target
        handled, remote_res = await _forward_if_remote(
            "send_terminal_input",
            {"worker_id": actual_id, "text": text, "press_enter": press_enter, "target": target},
        )
        if handled and isinstance(remote_res, str):
            return remote_res

        worker = mgr.get_worker(actual_id)
        if not worker:
            return f"Error: Worker '{actual_id}' not found."

        if not worker.is_alive:
            worker.restart()
            await asyncio.sleep(0.5)

        worker.write(text, press_enter=press_enter)
        return f"Input sent to worker '{actual_id}' ({len(text)} chars, enter={press_enter})."

    # ── Tool 4: interrupt_and_inject ──────────────────────────────────
    @server.tool()
    async def interrupt_and_inject(
        worker_id: str = "",
        sender_id: str = "primary-coordinator",
        message: str = "",
        priority: str = "high",
        target: str = "",
    ) -> str:
        """Pause ongoing action of the target agent with an interrupt and inject a priority directive safely.

        Sends an immediate interrupt (Ctrl+C / SIGINT) to pause the target `agy` agent,
        waits for the terminal prompt to settle without blocking the main event loop,
        and injects the incoming message formatted as:
        [INTERRUPT from {sender_id} | Priority: {priority}]: {message}
        Directive: Prioritize this message. Adjust plan and resume previous task only if no conflict.

        Args:
            worker_id: Identifier of the target worker agent to interrupt.
            sender_id: Identifier of the sender (e.g. 'primary-coordinator', 'supervisor').
            message: The interrupt explanation or new task directive to inject.
            priority: Priority level ('low', 'normal', 'high', 'critical'). Default is 'high'.
            target: Alias for worker_id.

        Returns:
            Confirmation of interrupt and injection.
        """
        actual_id = worker_id or target
        handled, remote_res = await _forward_if_remote(
            "interrupt_and_inject",
            {"worker_id": actual_id, "sender_id": sender_id, "message": message, "priority": priority, "target": target},
        )
        if handled and isinstance(remote_res, str):
            return remote_res

        worker = mgr.get_worker(actual_id)
        if not worker:
            return f"Error: Worker '{actual_id}' not found."

        if hasattr(worker, "interrupt_and_inject_async"):
            return await worker.interrupt_and_inject_async(
                sender_id=sender_id,
                message=message,
                priority=priority,
            )

        return worker.interrupt_and_inject(
            sender_id=sender_id,
            message=message,
            priority=priority,
        )

    # ── Tool 5: check_account_quotas ──────────────────────────────────
    @server.tool()
    async def check_account_quotas(
        slot: str = "",
        as_json: bool = False,
        hourly_limit: int | None = None,
        weekly_limit: int | None = None,
        target: str = "",
    ) -> dict[str, Any] | str:
        """Inspect accounts quota consumption and hourly/weekly limits for agy slots.

        Args:
            slot: Specific slot identifier (e.g. 'agy1', '1', or 'agy2'). If empty, checks all slots.
            as_json: Whether to return the result formatted as a raw JSON string.
            hourly_limit: Custom hourly limit override.
            weekly_limit: Custom weekly limit override.
            target: Alias for slot.

        Returns:
            Dictionary or JSON string containing quota consumption, remaining steps,
            status ('normal', 'warning', 'throttled'), and visual progress bars.
        """
        actual_slot = slot or target
        handled, remote_res = await _forward_if_remote(
            "check_account_quotas",
            {"slot": actual_slot, "as_json": as_json, "hourly_limit": hourly_limit, "weekly_limit": weekly_limit, "target": target},
        )
        if handled and isinstance(remote_res, (dict, str)):
            return remote_res

        if actual_slot:
            usage = usage_monitor.get_slot_usage(
                slot=actual_slot,
                hourly_limit=hourly_limit,
                weekly_limit=weekly_limit,
            )
            data: dict[str, Any] = {
                "slot": usage.slot,
                "account": usage.account,
                "email": usage.email,
                "token_status": usage.token_status,
                "token_expires_at": usage.token_expires_at.isoformat() if usage.token_expires_at else None,
                "token_remaining_seconds": usage.token_remaining_seconds,
                "hourly_used": usage.hourly_used,
                "hourly_limit": usage.hourly_limit,
                "hourly_remaining": usage.hourly_remaining,
                "hourly_remaining_percent": usage.hourly_remaining_percent,
                "weekly_used": usage.weekly_used,
                "weekly_limit": usage.weekly_limit,
                "weekly_remaining": usage.weekly_remaining,
                "weekly_remaining_percent": usage.weekly_remaining_percent,
                "status": usage.status.value,
                "is_throttled": usage.is_throttled,
                "throttle_reason": usage.throttle_reason,
                "progress_bar": usage.progress_bar,
                "colored_progress_bar": usage.colored_progress_bar,
            }
            if as_json:
                return json.dumps(data, indent=2, ensure_ascii=False)
            return data

        all_usages = usage_monitor.get_all_slots_usage(
            hourly_limit=hourly_limit,
            weekly_limit=weekly_limit,
        )
        summary_dict = usage_monitor.to_dict_summary(all_usages)
        if as_json:
            return json.dumps(summary_dict, indent=2, ensure_ascii=False)
        return summary_dict

    # ── Tool 6: get_agent_profile ─────────────────────────────────────
    @server.tool()
    async def get_agent_profile(
        agent_id: str = "",
        worker_id: str = "",
        target: str = "",
    ) -> dict[str, Any]:
        """Return role, principles, local `./agent` config, and assigned instructions.

        Args:
            agent_id: Identifier of the agent or worker.
            worker_id: Alias for agent_id.
            target: Alias for agent_id.

        Returns:
            Dictionary containing role, assigned task, principles, instructions, and config.
        """
        actual_id = agent_id or worker_id or target
        handled, remote_res = await _forward_if_remote(
            "get_agent_profile",
            {"agent_id": actual_id, "worker_id": worker_id, "target": target},
        )
        if handled and isinstance(remote_res, dict):
            return remote_res

        worker = mgr.get_worker(actual_id)
        if worker:
            return worker.get_profile_dict()

        for w in mgr.list_workers():
            if w.agent_id == actual_id:
                return w.get_profile_dict()

        return {
            "error": f"Agent '{actual_id}' not found in active sessions.",
            "available_agents": [w.agent_id for w in mgr.list_workers()],
        }

    # ── Tool 7: notify_coordinator_worker_idle ────────────────────────
    @server.tool()
    async def notify_coordinator_worker_idle(
        worker_id: str = "",
        status_summary: str = "",
        target: str = "",
    ) -> str:
        """Notify the Primary Coordinator that a worker has finished its task and is idle.

        Args:
            worker_id: Identifier of the worker agent that finished.
            status_summary: Optional summary of completed work or output.
            target: Alias for worker_id.

        Returns:
            Confirmation message and alarm event status.
        """
        actual_id = worker_id or target
        handled, remote_res = await _forward_if_remote(
            "notify_coordinator_worker_idle",
            {"worker_id": actual_id, "status_summary": status_summary, "target": target},
        )
        if handled and isinstance(remote_res, str):
            return remote_res

        if not actual_id:
            return "Error: worker_id must be provided."

        event = mgr.notify_coordinator_worker_idle(
            worker_id=actual_id,
            status_summary=status_summary,
        )
        return f"Coordinator notified: Worker '{actual_id}' is IDLE. (Alarm: {event.get('summary')})"

    # ── Tool 8: notify_coordinator_help ───────────────────────────────
    @server.tool()
    async def notify_coordinator_help(
        worker_id: str = "",
        reason: str = "",
        priority: str = "high",
        target: str = "",
    ) -> str:
        """Trigger an urgent assistance alarm to the Primary Coordinator from a worker agent.

        Args:
            worker_id: Identifier of the worker requiring assistance.
            reason: Explanation of the roadblock, error, or coordination need.
            priority: Severity level ('normal', 'high', 'critical').
            target: Alias for worker_id.

        Returns:
            Confirmation of dispatched alarm event.
        """
        actual_id = worker_id or target
        handled, remote_res = await _forward_if_remote(
            "notify_coordinator_help",
            {"worker_id": actual_id, "reason": reason, "priority": priority, "target": target},
        )
        if handled and isinstance(remote_res, str):
            return remote_res

        if not actual_id:
            return "Error: worker_id must be provided."

        mgr.notify_coordinator_worker_help(
            worker_id=actual_id,
            reason=reason,
            priority=priority,
        )
        return f"Coordinator assistance alarm emitted for Worker '{actual_id}' (Priority: {priority})."

    # ── Tool 9: check_coordinator_alarms ──────────────────────────────
    @server.tool()
    async def check_coordinator_alarms() -> list[dict[str, Any]]:
        """Retrieve unread alarm triggers, worker completion notices, and assistance requests.

        Returns:
            List of alarm event dictionaries queued for the coordinator.
        """
        handled, remote_res = await _forward_if_remote("check_coordinator_alarms", {})
        if handled and isinstance(remote_res, list):
            return remote_res

        return mgr.get_coordinator_alarms()

    return server


_global_server: FastMCP | None = None


def get_default_mcp_server() -> FastMCP:
    """Retrieve or create the default global MCP server instance."""
    global _global_server
    if _global_server is None:
        _global_server = create_mcp_server()
    return _global_server


def reset_default_mcp_server() -> None:
    """Reset the global default MCP server instance (primarily for test isolation)."""
    global _global_server
    _global_server = None
