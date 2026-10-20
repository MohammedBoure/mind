# `tests/` — Test Suite

This directory contains automated integration and unit test suites for `mind`.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Test package marker. |
| `test_integration.py` | Comprehensive test covering virtual screen buffer emulation (`pyte`), cross-platform PTY process spawning (`winpty`/Unix), embedded FastMCP tools (`list_workers`, `get_terminal_screen`, `send_terminal_input`, `interrupt_and_inject`, `get_agent_profile`), background SSE server runner, and Textual UI components. |
