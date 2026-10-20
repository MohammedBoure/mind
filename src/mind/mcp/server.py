"""Embedded MCP Server implementation for the mind multi-agent system.

Exposes tools for the primary coordinator agent to inspect worker terminal screens,
inject prioritized directives, control execution, and query worker profiles.
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]

from mind.core.terminal_manager import TerminalManager, WorkerSession

logger = logging.getLogger("mind.mcp")


def create_mcp_server(manager: TerminalManager | None = None) -> FastMCP:
    """Create and configure the mind-mcp server with all orchestration tools."""
    server = FastMCP(
        name="mind-mcp",
        instructions=(
            "Central MCP bridge for the mind AI Multi-Agent Orchestrator. "
            "Allows the primary coordinator agent to inspect live worker terminal screens, "
            "inject inter-agent interrupt directives, send raw inputs to worker terminals, "
            "and inspect agent profiles."
        ),
    )

    mgr = manager or TerminalManager.get_instance()

    # ── Tool 1: list_workers ──────────────────────────────────────────
    @server.tool()
    def list_workers() -> list[dict[str, Any]]:
        """List all active worker tabs, agent IDs, and their current process state.

        Returns:
            A list of dictionaries containing worker_id, agent_id, name,
            state ('running', 'paused', 'waiting_input', 'terminated'),
            process PID, model, task description, and unread notifications.
        """
        workers = mgr.list_workers()
        results: list[dict[str, Any]] = []
        for w in workers:
            results.append({
                "worker_id": w.worker_id,
                "agent_id": w.agent_id,
                "name": w.name,
                "state": w.state.value if hasattr(w.state, "value") else str(w.state),
                "pid": w.pid,
                "model": w.model,
                "task": w.task,
                "unread_notifications": w.unread_notifications,
                "is_alive": w.is_alive,
            })
        return results

    # ── Tool 2: get_terminal_screen ───────────────────────────────────
    @server.tool()
    def get_terminal_screen(worker_id: str = "", lines: int = 50, target: str = "") -> str:
        """Read the rendered clean text content from a worker's terminal screen buffer.

        Inspects what the worker agent is currently viewing or outputting in its terminal.

        Args:
            worker_id: The identifier of the worker agent (e.g. '1', 'worker-1').
            lines: Number of recent lines to retrieve (default: 50).
            target: Alias for worker_id.

        Returns:
            Rendered terminal text content, or an error message if not found.
        """
        actual_id = worker_id or target
        worker = mgr.get_worker(actual_id)
        if not worker:
            return f"Error: Worker '{actual_id}' not found. Available workers: {[w.worker_id for w in mgr.list_workers()]}"

        screen_text = worker.get_screen(lines=lines)
        if not screen_text.strip():
            return f"(Terminal buffer for Worker '{actual_id}' is currently empty or initializing)"
        return screen_text

    # ── Tool 3: send_terminal_input ───────────────────────────────────
    @server.tool()
    def send_terminal_input(
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
        worker = mgr.get_worker(actual_id)
        if not worker:
            return f"Error: Worker '{actual_id}' not found."

        if not worker.is_alive:
            return f"Error: Worker '{actual_id}' process is not alive."

        worker.write(text, press_enter=press_enter)
        return f"Input sent to worker '{actual_id}' ({len(text)} chars, enter={press_enter})."

    # ── Tool 4: interrupt_and_inject ──────────────────────────────────
    @server.tool()
    def interrupt_and_inject(
        worker_id: str = "",
        sender_id: str = "primary-agent",
        message: str = "",
        priority: str = "high",
        target: str = "",
    ) -> str:
        """Pause ongoing action of the target agent with an interrupt and inject a priority directive.

        Sends an immediate interrupt (Ctrl+C / SIGINT) to pause the target `agy` agent,
        waits for the terminal prompt to settle, and injects the incoming message formatted as:
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
        worker = mgr.get_worker(actual_id)
        if not worker:
            return f"Error: Worker '{actual_id}' not found."

        return worker.interrupt_and_inject(
            sender_id=sender_id,
            message=message,
            priority=priority,
        )

    # ── Tool 5: get_agent_profile ─────────────────────────────────────
    @server.tool()
    def get_agent_profile(
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
        worker = mgr.get_worker(actual_id)
        if worker:
            return worker.get_profile_dict()

        # Check if any worker matches agent_id attribute
        for w in mgr.list_workers():
            if w.agent_id == actual_id:
                return w.get_profile_dict()

        return {
            "error": f"Agent '{actual_id}' not found in active sessions.",
            "available_agents": [w.agent_id for w in mgr.list_workers()],
        }

    return server


_global_server: FastMCP | None = None


def get_default_mcp_server() -> FastMCP:
    """Retrieve or create the default global MCP server instance."""
    global _global_server
    if _global_server is None:
        _global_server = create_mcp_server()
    return _global_server
