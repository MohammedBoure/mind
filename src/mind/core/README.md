# `src/mind/core/` — Terminal & Process Multiplexing Core

This directory provides the low-level pseudoterminal (PTY) abstractions, virtual screen buffer emulation, and worker process lifecycle management for the `mind` multi-agent orchestrator.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public exports for core classes and helper factories. |
| `terminal_buffer.py` | Thread-safe 2D virtual screen and history buffer using `pyte.HistoryScreen` and `rich.text.Text`. Features high-performance run-length character batching, Style object caching, O(1) content checks, clean text export for MCP inspection, and ANSI rendering for Textual UI. |
| `pty_process.py` | Cross-platform PTY process spawner supporting Windows (`pywinpty` / ConPTY), Unix (`pty`/`termios`), and pipe fallbacks. Handles environment blocks for WinPTY, signal propagation (SIGINT/Ctrl+C), and zombie-safe process termination. |
| `agent_discovery.py` | System-wide Antigravity agent discovery (`discover_system_agents`): discovers installed CLI agents (`agy1`, `agy2`, etc.) via `agy agents`, slot launchers in `%LOCALAPPDATA%\agy\bin`, `~/.gemini/instances`, and tokens. |
| `credentials.py` | Backwards-compatible facade forwarding credential management, mutex locking, and environment setup to `mind.core.auth`. |
| `auth/` | Modular authentication package containing models, validator, keyring backends, mutex locking, and token manager. |
| `directives.py` | Directives and behavioral guidelines manager. Persists coordinator and worker rules to `~/.mind/directives/` and handles in-app/external editing. |
| `terminal_manager.py` | Central `TerminalManager` orchestrator and `WorkerSession` model. Manages active `agy` worker and coordinator sessions, slot credential isolation and restoration on startup, thread-storm debouncing, lazy worker lifecycle, CLI flags tuning (`--mode`, `--model`, `--effort`, extra flags), coordinator MCP prompt injection, process restarting (`restart_worker`), inter-agent interrupt directives, and notification dispatching. |
