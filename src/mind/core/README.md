# `src/mind/core/` — Terminal & Process Multiplexing Core

This directory provides the low-level pseudoterminal (PTY) abstractions, virtual screen buffer emulation, and worker process lifecycle management for the `mind` multi-agent orchestrator.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public exports for core classes and helper factories. |
| `terminal_buffer.py` | Thread-safe 2D virtual screen and history buffer using `pyte.HistoryScreen` and `rich.text.Text`. Provides clean text export for MCP inspection and ANSI rendering for Textual UI. |
| `pty_process.py` | Cross-platform PTY process spawner supporting Windows (`pywinpty` / ConPTY), Unix (`pty`/`termios`), and pipe fallbacks. Handles signal propagation (SIGINT/Ctrl+C) and zombie-safe process termination. |
| `terminal_manager.py` | Central `TerminalManager` orchestrator and `WorkerSession` model. Manages active `agy` worker sessions, CLI flags tuning (`--mode`, `--model`, `--effort`, extra flags), process restarting (`restart_worker`), inter-agent interrupt directives, and notification dispatching. |
