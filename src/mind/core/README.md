# `src/mind/core/` — Terminal & Process Multiplexing Core

This directory provides the low-level pseudoterminal (PTY) abstractions, virtual screen buffer emulation, and worker process lifecycle management for the `mind` multi-agent orchestrator.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public exports for core classes and helper factories. |
| `terminal_buffer.py` | Thread-safe 2D virtual character grid and scrollback history buffer using `pyte.HistoryScreen` and `rich.text.Text`. Features high-performance Run-Length Encoding (RLE) character batching, `rich.style.Style` object caching (preventing memory bloat), frame-level render caching to eliminate redundant re-rendering of unchanged frames, instant $O(1)$ version counter tracking and visible content presence detection, and clean ANSI-free plain text export functions (`get_screen_text`, `get_plain_text`, `export_clean_text`) for MCP tool inspection while preserving full formatting and colors for Textual TUI. |
| `pty_process.py` | High-performance, event-driven cross-platform PTY engine supporting Windows (ConPTY via `pywinpty` with dead-key blocking, scancode translation, and stray `\xe0` byte filtering), Linux/Unix (native `openpty`/`termios` with `epoll` selector reader), zero-polling event-driven async streams (<1ms latency), `SIGINT`/`Ctrl+C` propagation, and zombie process prevention via `psutil`. |
| `agent_discovery.py` | System-wide Antigravity agent discovery (`discover_system_agents`): discovers installed CLI agents (`agy1`, `agy2`, etc.) via `agy agents`, slot launchers in `%LOCALAPPDATA%\agy\bin`, `~/.gemini/instances`, and tokens. |
| `credentials.py` | Backwards-compatible facade forwarding credential management, mutex locking, and environment setup to `mind.core.auth`. |
| `auth/` | Modular authentication package containing models, validator, keyring backends, mutex locking, and token manager. |
| `directives.py` | Directives and behavioral guidelines manager. Persists coordinator and worker rules to `~/.mind/directives/` and handles in-app/external editing. |
| `terminal_manager.py` | Central `TerminalManager` orchestrator and `WorkerSession` model. Manages active `agy` worker and coordinator sessions, slot credential isolation and restoration on startup, thread-storm debouncing, lazy worker lifecycle, CLI flags tuning (`--mode`, `--model`, `--effort`, extra flags), coordinator MCP prompt injection, process restarting (`restart_worker`), inter-agent interrupt directives, and notification dispatching. |
