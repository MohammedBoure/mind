# `tui-core/src/` — Compiled TUI Engine Source Root

This directory contains the root source tree of `tui-core`.

## Files & Subdirectories

| File / Subdirectory | Purpose |
|---|---|
| `lib.rs` | Main library root exposing `TuiEngine`, public exports, and unified subsystem APIs. |
| `main.rs` | Application entrypoint providing interactive Ratatui TUI mode (`run`), stdio MCP server mode (`--mcp-stdio`), and performance benchmark runner (`bench`). |
| `error.rs` | Unified error types (`TuiError`) and Result type alias (`Result<T>`). |
| `pty/` | Low-level cross-platform PTY master process loop and virtual screen buffer emulator (`ScreenBuffer`). |
| `events/` | Unified Tokio asynchronous event loop multiplexing Crossterm input events, PTY streams, alarms, and timers. |
| `ipc/` | JSON-RPC 2.0 protocol implementation, MCP client for `mind-mcp`, and embedded MCP server. |
| `session/` | Multi-agent session orchestration, active worker tabs, and process lifecycle management (`SessionManager`, `WorkerSession`). |
