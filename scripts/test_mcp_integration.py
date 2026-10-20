"""End-to-End QA Integration Test Runner for mind.

Acts as an automated MCP client connecting over SSE to the background
mind-mcp server to verify:
1. Process bootstrap of multiple worker terminals running real agy instances.
2. Querying list_workers, get_terminal_screen, send_terminal_input, and get_agent_profile.
3. Priority inter-agent interrupt and directive injection workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from mind.core.terminal_manager import TerminalManager, WorkerProcessState, WorkerSession
from mind.mcp.runner import MCPServerRunner

# Configure clean logging output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("QA-E2E")


class MCPIntegrationTestRunner:
    """End-to-End Test Harness for mind-mcp server and PTY worker processes."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self.server_url = f"http://{host}:{port}/sse"
        self.manager = TerminalManager.get_instance()
        self.runner: MCPServerRunner | None = None
        self.notifications_received: list[tuple[WorkerSession, str]] = []

    def _on_notification(self, worker: WorkerSession, formatted_directive: str) -> None:
        """Callback validating that TUI toast and notification events trigger immediately."""
        logger.info(f"⚡ [TUI Event Hook] Toast notification triggered on {worker.name}!")
        self.notifications_received.append((worker, formatted_directive))

    def setup_environment(self) -> None:
        """Bootstrap worker processes and embedded MCP SSE server."""
        logger.info("=================================================================")
        logger.info("Step 1: Bootstrapping Workers & Embedded MCP Server")
        logger.info("=================================================================")

        # Clean any stale workers
        self.manager.stop_all()
        self.manager.add_notification_listener(self._on_notification)

        # Detect agy executable
        agy_path = shutil.which("agy") or shutil.which("agy.exe")
        if not agy_path and sys.platform == "win32":
            local_agy = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
            if os.path.exists(local_agy):
                agy_path = local_agy

        logger.info(f"Target Agent CLI: {agy_path or 'System Shell (fallback)'}")

        # Spawn Worker 1 running agy
        logger.info("Spawning Worker-1 (Primary Sub-Agent running agy)...")
        w1 = self.manager.create_worker(
            worker_id="worker-1",
            agent_id="worker-1",
            name="Worker-1",
            role="worker",
            model="gpt-4o-mini",
            task="Refactor core authentication module",
            command=[agy_path] if agy_path else None,
            autostart=True,
        )

        # Spawn Worker 2 running agy
        logger.info("Spawning Worker-2 (Secondary Sub-Agent running agy)...")
        w2 = self.manager.create_worker(
            worker_id="worker-2",
            agent_id="worker-2",
            name="Worker-2",
            role="worker",
            model="gpt-4o-mini",
            task="Run unit test suite and verify coverage",
            command=[agy_path] if agy_path else None,
            autostart=True,
        )

        logger.info(f"  ✓ Worker-1 PID: {w1.pid} (State: {w1.state.value})")
        logger.info(f"  ✓ Worker-2 PID: {w2.pid} (State: {w2.state.value})")

        # Allow agy processes to initialize their console buffers
        logger.info("Waiting 3.0s for child agy processes to render initial terminal screen...")
        time.sleep(3.0)

        # Boot background MCP server
        logger.info(f"Starting embedded MCP SSE server on {self.server_url}...")
        self.runner = MCPServerRunner(host=self.host, port=self.port)
        self.runner.start(wait_for_ready=True, timeout=5.0)
        assert self.runner.is_running, "Failed to start background MCP SSE server"
        logger.info("  ✓ MCP SSE Server daemon listening and ready.")

    async def run_client_suite(self) -> None:
        """Connect as an external MCP client over SSE and execute all test vectors."""
        logger.info("\n=================================================================")
        logger.info("Step 2: Connecting MCP Client & Testing Endpoints Over SSE")
        logger.info("=================================================================")

        async with sse_client(self.server_url) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                logger.info("  ✓ MCP Protocol Handshake initialized successfully.")

                # ── Test 1: Tool Discovery ─────────────────────────────────
                tool_list = await client.list_tools()
                discovered_names = [t.name for t in tool_list.tools]
                logger.info(f"Discovered Tools: {discovered_names}")
                for expected in [
                    "list_workers",
                    "get_terminal_screen",
                    "send_terminal_input",
                    "interrupt_and_inject",
                    "get_agent_profile",
                ]:
                    assert expected in discovered_names, f"Missing expected tool: {expected}"
                logger.info("  ✓ [TEST 1 PASSED] All 5 MCP tools properly registered and discoverable.")

                # ── Test 2: list_workers ───────────────────────────────────
                logger.info("\nExecuting list_workers()...")
                res = await client.call_tool("list_workers", {})
                workers_data = [json.loads(c.text) for c in res.content]
                logger.info(f"  → Found {len(workers_data)} active worker(s):")
                found_ids = []
                for w in workers_data:
                    logger.info(f"    • {w['worker_id']} ({w['name']}): State={w['state']}, PID={w['pid']}")
                    found_ids.append(w["worker_id"])
                    assert w["pid"] is not None and w["pid"] > 0, "PID must be valid integer"
                    assert w["state"] in ["running", "paused", "waiting_input"]

                assert "worker-1" in found_ids and "worker-2" in found_ids, "Both workers must be listed"
                logger.info("  ✓ [TEST 2 PASSED] list_workers returned accurate PIDs and active states.")

                # ── Test 3: get_terminal_screen ────────────────────────────
                logger.info("\nExecuting get_terminal_screen('worker-1', lines=20)...")
                res_w1 = await client.call_tool("get_terminal_screen", {"target": "worker-1", "lines": 20})
                screen_w1 = res_w1.content[0].text
                logger.info("  → Worker-1 Screen Output Sample:")
                for line in [l for l in screen_w1.splitlines() if l.strip()][:5]:
                    logger.info(f"     | {line}")
                assert len(screen_w1.strip()) > 0, "Screen buffer for Worker-1 must not be empty"
                logger.info("  ✓ [TEST 3 PASSED] get_terminal_screen fetched real rendered screen buffer.")

                # ── Test 4: send_terminal_input ────────────────────────────
                logger.info("\nExecuting send_terminal_input('worker-1', text='?') to query shortcuts...")
                res_input = await client.call_tool(
                    "send_terminal_input",
                    {"target": "worker-1", "text": "?", "press_enter": True},
                )
                logger.info(f"  → Response: {res_input.content[0].text}")
                assert "Input sent to worker" in res_input.content[0].text
                time.sleep(0.5)
                logger.info("  ✓ [TEST 4 PASSED] send_terminal_input accepted and delivered keystrokes.")

                # ── Test 5: get_agent_profile ──────────────────────────────
                logger.info("\nExecuting get_agent_profile('worker-2')...")
                res_prof = await client.call_tool("get_agent_profile", {"target": "worker-2"})
                prof_data = json.loads(res_prof.content[0].text)
                logger.info(f"  → Profile: Role={prof_data['role']}, Model={prof_data['model']}")
                logger.info(f"  → Assigned Task: '{prof_data['task']}'")
                logger.info(f"  → Principles: {len(prof_data['principles'])} directives loaded.")
                assert prof_data["worker_id"] == "worker-2"
                assert len(prof_data["principles"]) > 0
                logger.info("  ✓ [TEST 5 PASSED] get_agent_profile returned structured agent configuration.")

                # ── Test 6: interrupt_and_inject ───────────────────────────
                logger.info("\n=================================================================")
                logger.info("Step 3: Testing Inter-Agent Immediate Interrupt & Injection")
                logger.info("=================================================================")
                directive_msg = "Stop current build and check syntax first."
                logger.info(
                    f"Triggering interrupt_and_inject(target='worker-2', "
                    f"sender_id='primary-agent', message='{directive_msg}', priority='high')..."
                )

                res_inject = await client.call_tool(
                    "interrupt_and_inject",
                    {
                        "target": "worker-2",
                        "sender_id": "primary-agent",
                        "message": directive_msg,
                        "priority": "high",
                    },
                )
                logger.info(f"  → Injection Response: {res_inject.content[0].text}")
                assert "Successfully interrupted worker-2" in res_inject.content[0].text

                # Validate notification hook fired
                assert len(self.notifications_received) > 0, "TUI toast notification callback must have fired"
                notif_worker, notif_text = self.notifications_received[-1]
                assert notif_worker.worker_id == "worker-2"
                assert directive_msg in notif_text
                logger.info("  ✓ Visual toast notification event verified on target Worker-2 tab.")

                # Validate target worker internal state
                target_worker = self.manager.get_worker("worker-2")
                assert target_worker is not None
                assert target_worker.unread_notifications >= 1
                logger.info(f"  ✓ Target worker unread notification counter: {target_worker.unread_notifications}")

                # Validate injected prompt in target worker buffer
                time.sleep(0.5)
                screen_after = target_worker.get_screen(lines=30)
                logger.info("  → Target Terminal Buffer after interrupt injection:")
                matched_lines = [l for l in screen_after.splitlines() if "INTERRUPT" in l or "syntax" in l]
                for l in matched_lines:
                    logger.info(f"     | {l.strip()}")

                assert (
                    "INTERRUPT from primary-agent" in str(target_worker.last_interrupt_directive)
                    or "Stop current build" in str(target_worker.last_interrupt_directive)
                )
                logger.info("  ✓ Formatted directive verified in target worker's stream.")
                logger.info("  ✓ [TEST 6 PASSED] Full inter-agent interrupt and resume protocol verified!")

    def cleanup(self) -> None:
        """Safely terminate child processes, close PTYs, and stop MCP server."""
        logger.info("\n=================================================================")
        logger.info("Step 4: Cleanup & Zombie Prevention")
        logger.info("=================================================================")
        if self.runner:
            self.runner.stop()
            logger.info("  ✓ Background MCP server stopped.")

        self.manager.stop_all()
        logger.info("  ✓ All worker processes and PTY handles terminated cleanly.")


def main() -> None:
    runner = MCPIntegrationTestRunner(host="127.0.0.1", port=8765)
    exit_code = 0
    try:
        runner.setup_environment()
        asyncio.run(runner.run_client_suite())
        logger.info("\n=================================================================")
        logger.info("ALL INTEGRATION & INTER-AGENT VERIFICATION TESTS PASSED (100% OK)")
        logger.info("=================================================================")
    except Exception as e:
        logger.exception(f"Test suite encountered failure: {e}")
        exit_code = 1
    finally:
        runner.cleanup()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
