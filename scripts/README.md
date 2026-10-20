# `scripts/` — Automated QA & Integration Scripts

This directory contains standalone testing, benchmarking, and verification scripts for the `mind` system.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Scripts module marker. |
| `test_mcp_integration.py` | Automated end-to-end QA test suite acting as an MCP client over SSE. Bootstraps worker `agy` processes, queries `list_workers`, fetches screen buffers with `get_terminal_screen`, sends inputs with `send_terminal_input`, tests immediate interrupt directives with `interrupt_and_inject`, and validates agent profiles with `get_agent_profile`. |
