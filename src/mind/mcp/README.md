# `src/mind/mcp/` — High-Performance Async Model Context Protocol (MCP) Server

This directory contains the embedded MCP server (`mind-mcp`) that exposes lightweight, asyncio-native orchestration tools for the primary coordinator agent to inspect worker terminal screens, inject prioritized interrupts, deliver direct inputs, monitor account quotas, and coordinate tasks across multiple agents.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public exports for MCP server creation (`create_mcp_server`, `get_default_mcp_server`, `reset_default_mcp_server`), background daemon runner (`MCPServerRunner`, `start_background_mcp_server`, `stop_background_mcp_server`), screen buffer cache (`TerminalScreenCache`), and stdio entrypoints (`run_stdio_mcp_server`, `run_stdio_mcp_server_async`). |
| `server.py` | FastMCP / MCPServer definition exposing ultra-lightweight async MCP tools: `list_workers` (with linked accounts and quota statistics), `get_terminal_screen` (version-tracked cached screen reader), `send_terminal_input` (direct stdin dispatch), `interrupt_and_inject` (safe SIGINT pause and prioritized directive injection), `check_account_quotas` (hourly/weekly quota inspector with colored progress bars), `get_agent_profile`, `notify_coordinator_worker_idle`, `notify_coordinator_help`, and `check_coordinator_alarms`. |
| `runner.py` | Dual-transport execution runner supporting: (1) local HTTP SSE server (`uvicorn.Server` on `127.0.0.1:8765`) running fully asynchronously in background without blocking the main application lifecycle (`wait_for_ready=False`), (2) automatic provisioning and persistence of `mind-mcp` across orchestrator instances (`provision_mcp_config`), and (3) Standard I/O (stdio) transport for direct pairing with Antigravity CLI (`mind mcp` / `agy.exe mcp add mind-mcp`). |

## Exposed MCP Tools

1. **`list_workers()`**
   - Returns operational status, PIDs, tasks, and linked slot/account identities (`slot_id`, `assigned_agent`, `linked_account`, `token_status`, `quota_status`, `hourly_remaining`, `weekly_remaining`).
2. **`get_terminal_screen(worker_id, lines=50)`**
   - Reads clean, ANSI-free rendered text from any worker's virtual terminal buffer (use `lines=0` to retrieve the entire buffer including full scrollback history uncapped).
   - Utilizes `TerminalScreenCache` to provide instant $O(1)$ responses when buffer version is unchanged.
3. **`send_terminal_input(worker_id, text, press_enter=True)`**
   - Dispatches raw commands and keystrokes directly to the target worker process stdin.
4. **`interrupt_and_inject(worker_id, sender_id, message, priority='high')`**
   - Emits an immediate `SIGINT` / `Ctrl+C` interrupt signal to pause the target `agy` agent safely, allows prompt to stabilize asynchronously without blocking the event loop, and writes formatted priority directives.
5. **`check_account_quotas(slot='', as_json=False, hourly_limit=None, weekly_limit=None)`**
   - Inspects hourly and weekly quota consumption for one or all slots, calculating remaining steps and graphic progress bars (`[████████░░] 80%`).
6. **`get_agent_profile(agent_id)`**
   - Returns agent configuration, role, principles, local `./agent` configs, and instructions.
7. **`notify_coordinator_worker_idle(worker_id, status_summary)`**
   - Emits an idle completion alarm event to the primary coordinator.
8. **`notify_coordinator_help(worker_id, reason, priority='high')`**
   - Dispatches an urgent assistance request from a worker agent to the coordinator.
9. **`check_coordinator_alarms()`**
   - Retrieves queued alarm events and notifications for the coordinator.
