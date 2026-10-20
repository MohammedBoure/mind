# `src/mind/mcp/` — Embedded Model Context Protocol (MCP) Server

This directory contains the embedded MCP server (`mind-mcp`) that exposes worker terminal inspection, prioritized interrupt injection, and process control to primary coordinator agents.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public exports for MCP server creation, background daemon runner, and stdio entrypoint. |
| `server.py` | FastMCP / MCPServer definition exposing `list_workers`, `get_terminal_screen`, `send_terminal_input`, `interrupt_and_inject`, and `get_agent_profile`. |
| `runner.py` | Background HTTP/SSE runner (`uvicorn.Server` on `127.0.0.1:8765`) and foreground stdio runner. |
