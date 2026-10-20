# `tests/` — Test Suite

This directory contains automated integration and unit test suites for `mind`.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Test package marker. |
| `test_integration.py` | Comprehensive test covering virtual screen buffer emulation (`pyte`), cross-platform PTY process spawning (`winpty`/Unix), embedded FastMCP tools (`list_workers`, `get_terminal_screen`, `send_terminal_input`, `interrupt_and_inject`, `get_agent_profile`), background SSE server runner, and Textual UI components. |
| `test_vim_modal.py` | Unit tests for the Vim Modal System, visible worker tab bar, split-view toggling ('s'), agent task assignment dispatcher, and PTY input isolation. |
| `test_credentials_isolation.py` | Tests for multi-slot authentication persistence, environment directory isolation (`AGY_SLOT`, `ANTIGRAVITY_GEMINI_DIR`, `ANTIGRAVITY_APP_DATA_DIR`), cross-process credential mutex locks, BOM-safe token decoding, and non-destructive shutdown. |
| `test_auth_refactor.py` | Unit tests for modular authentication architecture: BOM sanitization, claims decoding, expiration detection, mock storage, and token lifecycle manager. |
| `test_directives_and_idle.py` | Unit tests for passive idle startup, Markdown directive file persistence in `~/.mind/directives/`, in-app editing, and event-driven coordinator wake-up alarms. |
