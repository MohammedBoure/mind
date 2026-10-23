# `tui-core/src/` — Compiled TUI Engine Source Root

This directory contains the root source tree of `tui-core`.

## Architectural Summary

`tui-core` is organized into focused, modular subsystems:
- **Presentation & UX (`ui/`)**: Ratatui widgets, responsive split panes, status bars, quota progress gauges, dynamic worker lists, and accessible theme systems (Tokyo Night, High Contrast Dark/Light, and Color-Blind universal design).
- **Asynchronous Event Engine (`events/`)**: Tokio event multiplexer combining Crossterm keystrokes, POSIX `SIGWINCH` window change signals, PTY output chunks, and coordinator alarms.
- **Pseudo-Terminal Master Engine (`pty/`)**: Cross-platform PTY management with `portable-pty` and ANSI/VTE virtual screen buffer emulator (`ScreenBuffer`) with scrollback history and dynamic resizing.
- **Session & Swarm Management (`session/`)**: Multi-agent lifecycle management, active focus switching (`Tab`, `Shift+Tab`, `Alt+1`..`Alt+9`), scrollback navigation offsets, and graceful child shutdown.
- **Model Context Protocol Bridge (`ipc/`)**: JSON-RPC 2.0 framing, embedded stdio tool dispatch server, and asynchronous HTTP/SSE client.

## Files & Subdirectories

| File / Subdirectory | Purpose |
|---|---|
| [`lib.rs`](file:///home/pluto/projects/mind/tui-core/src/lib.rs) | Main library root exposing `TuiEngine`, public exports, and unified subsystem facades. |
| [`main.rs`](file:///home/pluto/projects/mind/tui-core/src/main.rs) | Application entrypoint providing interactive Ratatui TUI mode (`run`), stdio MCP server mode (`--mcp-stdio`), and performance benchmark runner (`bench`). |
| [`error.rs`](file:///home/pluto/projects/mind/tui-core/src/error.rs) | Unified error taxonomy (`TuiError`) and Result type alias (`Result<T>`). |
| [`benchmarks.rs`](file:///home/pluto/projects/mind/tui-core/src/benchmarks.rs) | In-engine benchmark suite measuring frame render latency, PTY ingestion rates, and memory consumption. |
| [`pty/`](file:///home/pluto/projects/mind/tui-core/src/pty/README.md) | Low-level cross-platform PTY master process loop and virtual screen buffer emulator (`ScreenBuffer`). |
| [`events/`](file:///home/pluto/projects/mind/tui-core/src/events/README.md) | Unified Tokio asynchronous event loop multiplexing Crossterm input events, POSIX SIGWINCH signals, PTY streams, alarms, and timers. |
| [`ipc/`](file:///home/pluto/projects/mind/tui-core/src/ipc/README.md) | JSON-RPC 2.0 protocol implementation, MCP client for `mind-mcp`, and embedded MCP server. |
| [`session/`](file:///home/pluto/projects/mind/tui-core/src/session/README.md) | Multi-agent session orchestration, active worker tabs, scrollback offsets, and process lifecycle management (`SessionManager`, `WorkerSession`). |
| [`ui/`](file:///home/pluto/projects/mind/tui-core/src/ui/README.md) | Reusable accessible visual widgets (`SplitPanesWidget`, `StatusBarWidget`, `QuotaGaugesWidget`, `WorkerListWidget`, `TerminalScreenWidget`, `Theme`). |
